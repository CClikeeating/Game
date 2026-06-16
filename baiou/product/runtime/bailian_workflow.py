from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class BailianWorkflowClient:
    def __init__(self, name: str, config: dict[str, Any], app_id: str, user_id: str):
        self.name = name
        self.config = config
        self.app_id = str(app_id).strip()
        self.user_id = str(user_id)
        self.api_key = os.environ.get(str(config.get("api_key_env", "")), "")

    def available(self) -> tuple[bool, str]:
        if not self.config.get("enabled", False):
            return False, f"{self.name}_disabled"
        if not self.app_id:
            return False, f"{self.name}_missing_app_id"
        if not endpoint_url(self.config, self.app_id):
            return False, f"{self.name}_missing_endpoint"
        if not self.api_key:
            return False, f"{self.name}_missing_api_key"
        return True, "available"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        ok, reason = self.available()
        if not ok:
            return self._result("workflow_unavailable", reason, "", {}, started)

        request = urllib.request.Request(
            endpoint_url(self.config, self.app_id),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.config.get("timeout_seconds", 180))) as response:
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:1600]
            return self._result("workflow_call_failed", f"http_{exc.code}: {detail}", "", {}, started)
        except Exception as exc:  # noqa: BLE001 - product runtime should report failures, not crash.
            return self._result("workflow_call_failed", exc.__class__.__name__, "", {}, started)

        try:
            raw_response = json.loads(raw_text)
        except json.JSONDecodeError:
            return self._result("workflow_response_invalid", "invalid_json_response", raw_text, {}, started)
        return self._result("workflow_success", "", raw_text, raw_response, started)

    def _result(self, status: str, error: str, raw_text: str, raw_response: dict[str, Any], started: float) -> dict[str, Any]:
        return {
            "client": self.name,
            "provider": self.config.get("provider", "bailian"),
            "model": self.config.get("model", "bailian_workflow_app"),
            "app_id": self.app_id,
            "user_id": self.user_id,
            "status": status,
            "error": error,
            "elapsed_seconds": round(time.time() - started, 2),
            "raw_text": raw_text,
            "raw_response": raw_response,
            "usage": extract_usage(raw_response),
            "response_debug": summarize_response(raw_response, raw_text),
        }


def endpoint_url(config: dict[str, Any], app_id: str) -> str:
    endpoint = str(config.get("endpoint", "")).strip()
    if endpoint:
        return endpoint.format(app_id=app_id)
    base_url = str(config.get("base_url", "")).strip().rstrip("/")
    endpoint_path = str(config.get("endpoint_path", "")).strip()
    if not base_url or not endpoint_path:
        return ""
    return base_url + "/" + endpoint_path.lstrip("/").format(app_id=app_id)


def extract_usage(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("usage", "token_usage"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    output = data.get("output")
    if isinstance(output, dict):
        usage = output.get("usage") or output.get("token_usage")
        if isinstance(usage, dict):
            return usage
    return {}


def summarize_response(data: dict[str, Any], raw_text: str) -> dict[str, Any]:
    return {
        "top_level_keys": sorted(data.keys()) if isinstance(data, dict) else [],
        "raw_preview": trim_text(raw_text, 8000),
    }


def trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= max_chars else text[:max_chars] + "\n...[truncated]"
