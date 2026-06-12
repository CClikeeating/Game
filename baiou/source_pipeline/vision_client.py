from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class VisionClient:
    def __init__(self, config: dict[str, Any], prompt_config: dict[str, Any]):
        self.config = config
        self.prompt_config = prompt_config
        self.api_key = os.environ.get(str(config.get("api_key_env", "")), "")

    def available(self) -> tuple[bool, str]:
        if not self.config.get("enabled", False):
            return False, "vision_model_disabled"
        if self.config.get("api_style") not in {"openai_compatible_vision", "dashscope_multimodal"}:
            return False, "unsupported_vision_api_style"
        if not self.api_key:
            return False, "vision_model_missing_api_key"
        return True, "available"

    def extract_turns(self, case_id: str, image_items: list[dict[str, Any]], mode: str) -> dict[str, Any]:
        if self.config.get("api_style") == "dashscope_multimodal":
            return self.extract_turns_dashscope(case_id, image_items, mode)
        return self.extract_turns_openai_compatible(case_id, image_items, mode)

    def extract_turns_openai_compatible(
        self,
        case_id: str,
        image_items: list[dict[str, Any]],
        mode: str,
    ) -> dict[str, Any]:
        available, reason = self.available()
        if not available:
            return {"status": "model_unavailable", "error": reason, "raw_text": "", "parsed": {}}
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "case_id": case_id,
                        "mode": mode,
                        "instruction": self.prompt_config["user_prompt"],
                        "blocks": [
                            {
                                "block_id": item["block_id"],
                                "order": item["order"],
                                "crop_box": item.get("crop_box", []),
                                "source_ref": item.get("source_ref", ""),
                            }
                            for item in image_items
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        for item in image_items:
            content.append({"type": "text", "text": block_context_label(item)})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_url(Path(item["prepared_path"])),
                        "detail": self.config.get("image_detail", "auto"),
                    },
                }
            )
        payload = {
            "model": self.config["model"],
            "temperature": self.config.get("temperature", 0.0),
            "messages": [
                {"role": "system", "content": self.prompt_config["system_prompt"]},
                {"role": "user", "content": content},
            ],
        }
        user_id = str(self.config.get("user_id", "")).strip()
        if user_id:
            payload["user_id"] = user_id
        url = str(self.config["base_url"]).rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.config.get("timeout_seconds", 120))) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return {"status": "model_call_failed", "error": f"http_{exc.code}", "raw_text": "", "parsed": {}}
        except Exception as exc:  # noqa: BLE001 - experiment should continue and report failures.
            return {"status": "model_call_failed", "error": exc.__class__.__name__, "raw_text": "", "parsed": {}}
        raw_text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        parsed = parse_json_content(raw_text)
        if not isinstance(parsed, dict):
            return {"status": "model_json_invalid", "error": "", "raw_text": raw_text, "parsed": {}}
        return {"status": "model_success", "error": "", "raw_text": raw_text, "parsed": parsed}

    def extract_turns_dashscope(self, case_id: str, image_items: list[dict[str, Any]], mode: str) -> dict[str, Any]:
        available, reason = self.available()
        if not available:
            return {"status": "model_unavailable", "error": reason, "raw_text": "", "parsed": {}}

        content: list[dict[str, Any]] = []
        content.append(
            {
                "text": json.dumps(
                    {
                        "case_id": case_id,
                        "mode": mode,
                        "instruction": self.prompt_config["user_prompt"],
                        "blocks": [
                            {
                                "block_id": item["block_id"],
                                "order": item["order"],
                                "crop_box": item.get("crop_box", []),
                                "source_ref": item.get("source_ref", ""),
                            }
                            for item in image_items
                        ],
                    },
                    ensure_ascii=False,
                )
            }
        )
        for item in image_items:
            content.append({"text": block_context_label(item)})
            content.append({"image": image_data_url(Path(item["prepared_path"]))})

        payload = {
            "model": self.config["model"],
            "input": {
                "messages": [
                    {"role": "system", "content": [{"text": self.prompt_config["system_prompt"]}]},
                    {"role": "user", "content": content},
                ]
            },
            "parameters": {
                "temperature": self.config.get("temperature", 0.0),
                "result_format": "message",
            },
        }
        user_id = str(self.config.get("user_id", "")).strip()
        if user_id:
            payload["user_id"] = user_id
        request = urllib.request.Request(
            str(self.config["base_url"]),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.config.get("timeout_seconds", 120))) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")[:800]
            return {"status": "model_call_failed", "error": f"http_{exc.code}: {details}", "raw_text": "", "parsed": {}}
        except Exception as exc:  # noqa: BLE001 - experiment should continue and report failures.
            return {"status": "model_call_failed", "error": exc.__class__.__name__, "raw_text": "", "parsed": {}}

        message = (
            data.get("output", {})
            .get("choices", [{}])[0]
            .get("message", {})
        )
        content_out = message.get("content", "")
        if isinstance(content_out, list):
            raw_text = "\n".join(str(item.get("text", "")) for item in content_out if isinstance(item, dict))
        else:
            raw_text = str(content_out)
        raw_text = raw_text.strip()
        parsed = parse_json_content(raw_text)
        if not isinstance(parsed, dict):
            return {"status": "model_json_invalid", "error": "", "raw_text": raw_text, "parsed": {}}
        return {"status": "model_success", "error": "", "raw_text": raw_text, "parsed": parsed}


def block_context_label(item: dict[str, Any]) -> str:
    return json.dumps(
        {
            "block_id": item.get("block_id", ""),
            "order": item.get("order", ""),
            "crop_box": item.get("crop_box", []),
            "overlap_top": item.get("overlap_top", 0),
            "overlap_bottom": item.get("overlap_bottom", 0),
            "source_ref": item.get("source_ref", ""),
            "note": "overlap_top/overlap_bottom are context overlap zones; do not output duplicate turns from overlap areas.",
        },
        ensure_ascii=False,
    )


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def parse_json_content(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


