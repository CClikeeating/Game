from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class RuntimeModelClient:
    def __init__(self, name: str, config: dict[str, Any], user_id: str):
        self.name = name
        self.config = config
        self.user_id = user_id
        self.api_key = os.environ.get(str(config.get("api_key_env", "")), "")

    def available(self, needs_images: bool) -> tuple[bool, str]:
        if not self.config.get("enabled", False):
            return False, f"{self.name}_disabled"
        api_style = str(self.config.get("api_style", ""))
        if needs_images and api_style != "openai_compatible_vision":
            return False, f"{self.name}_does_not_support_images"
        if not needs_images and api_style not in {
            "openai_compatible_chat",
            "openai_compatible_vision",
            "openai_compatible_responses_file_search",
        }:
            return False, f"{self.name}_unsupported_api_style"
        if not self.api_key:
            return False, f"{self.name}_missing_api_key"
        return True, "available"

    def chat(self, system_prompt: str, user_prompt: str, image_paths: list[Path]) -> dict[str, Any]:
        started = time.time()
        available, reason = self.available(needs_images=bool(image_paths))
        if not available:
            return self._result("model_unavailable", reason, "", {}, started)
        if not image_paths and self.config.get("api_style") == "openai_compatible_responses_file_search":
            return self._responses_file_search(system_prompt, user_prompt, started)

        user_content: str | list[dict[str, Any]]
        if image_paths:
            user_content = [{"type": "text", "text": user_prompt}]
            for index, image_path in enumerate(image_paths, start=1):
                user_content.append({"type": "text", "text": f"用户上传图片 #{index}: {image_path.name}"})
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url(image_path),
                            "detail": self.config.get("image_detail", "auto"),
                        },
                    }
                )
        else:
            user_content = user_prompt

        payload: dict[str, Any] = {
            "model": self.config["model"],
            "max_tokens": self.config.get("max_tokens", 5000),
            "temperature": self.config.get("temperature", 0.2),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "user_id": str(self.user_id),
        }
        url = str(self.config["base_url"]).rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.config.get("timeout_seconds", 180))) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:1600]
            return self._result("model_call_failed", f"http_{exc.code}: {detail}", "", {}, started)
        except Exception as exc:  # noqa: BLE001 - runtime should return a report, not crash.
            return self._result("model_call_failed", exc.__class__.__name__, "", {}, started)

        raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        result = self._result("model_success", "", raw_text, data.get("usage", {}), started)
        return result

    def _responses_file_search(self, system_prompt: str, user_prompt: str, started: float) -> dict[str, Any]:
        file_search = self.config.get("file_search", {}) if isinstance(self.config.get("file_search"), dict) else {}
        tools = []
        if file_search.get("enabled", False):
            tool: dict[str, Any] = {
                "type": "file_search",
                "vector_store_ids": file_search.get("vector_store_ids", []),
            }
            if file_search.get("max_num_results"):
                tool["max_num_results"] = int(file_search["max_num_results"])
            tools.append(tool)
        payload: dict[str, Any] = {
            "model": self.config["model"],
            "instructions": system_prompt,
            "input": user_prompt,
            "tools": tools,
            "temperature": self.config.get("temperature", 0.2),
            "max_output_tokens": self.config.get("max_tokens", 5000),
            "user_id": str(self.user_id),
        }
        url = str(self.config["base_url"]).rstrip("/") + "/responses"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.config.get("timeout_seconds", 180))) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:1600]
            return self._result("model_call_failed", f"http_{exc.code}: {detail}", "", {}, started)
        except Exception as exc:  # noqa: BLE001 - runtime should return a report, not crash.
            return self._result("model_call_failed", exc.__class__.__name__, "", {}, started)

        raw_text = extract_response_text(data)
        return self._result("model_success", "", raw_text, data.get("usage", {}), started)

    def _result(
        self,
        status: str,
        error: str,
        raw_text: str,
        usage: dict[str, Any],
        started: float,
    ) -> dict[str, Any]:
        return {
            "client": self.name,
            "provider": self.config.get("provider", ""),
            "model": self.config.get("model", ""),
            "user_id": str(self.user_id),
            "status": status,
            "error": error,
            "elapsed_seconds": round(time.time() - started, 2),
            "raw_text": raw_text,
            "usage": usage,
        }


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_response_text(data: dict[str, Any]) -> str:
    direct = str(data.get("output_text", "")).strip()
    if direct:
        return direct
    chunks = []
    for item in data.get("output", []) if isinstance(data.get("output", []), list) else []:
        for content in item.get("content", []) if isinstance(item, dict) else []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("content")
            if text:
                chunks.append(str(text))
    return "\n".join(chunks).strip()
