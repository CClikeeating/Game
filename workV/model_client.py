from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class ChatJsonClient:
    def __init__(self, name: str, config: dict[str, Any], user_id: str):
        self.name = name
        self.config = config
        self.user_id = str(user_id)
        self.api_key = os.environ.get(str(config.get("api_key_env", "")), "")

    def available(self) -> tuple[bool, str]:
        if not self.config.get("enabled", False):
            return False, f"{self.name}_disabled"
        if self.config.get("api_style") != "openai_compatible_chat":
            return False, f"{self.name}_unsupported_api_style"
        if not self.api_key:
            return False, f"{self.name}_missing_api_key"
        return True, "available"

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        started = time.time()
        ok, reason = self.available()
        if not ok:
            return self._result("model_unavailable", reason, "", {}, started)
        payload: dict[str, Any] = {
            "model": self.config["model"],
            "temperature": self.config.get("temperature", 0.2),
            "max_tokens": self.config.get("max_tokens", 5000),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "user_id": self.user_id,
        }
        if self.config.get("response_format_json", False):
            payload["response_format"] = {"type": "json_object"}
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
        except Exception as exc:  # noqa: BLE001
            return self._result("model_call_failed", exc.__class__.__name__, "", {}, started)
        raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        parsed = parse_json_content(raw_text)
        if not isinstance(parsed, dict):
            return self._result("model_json_invalid", "", raw_text, {}, started)
        result = self._result("model_success", "", raw_text, parsed, started)
        result["usage"] = data.get("usage", {})
        return result

    def _result(self, status: str, error: str, raw_text: str, parsed: dict[str, Any], started: float) -> dict[str, Any]:
        return {
            "client": self.name,
            "provider": self.config.get("provider", ""),
            "model": self.config.get("model", ""),
            "user_id": self.user_id,
            "status": status,
            "error": error,
            "elapsed_seconds": round(time.time() - started, 2),
            "raw_text": raw_text,
            "parsed": parsed,
            "usage": {},
        }


def parse_json_content(content: str) -> Any:
    text = str(content or "").strip()
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
