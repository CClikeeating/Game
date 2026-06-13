from __future__ import annotations

import re
from typing import Any

from .common import load_config

SEGMENT_FIELDS = [
    "case_id",
    "schema_version",
    "segment_id",
    "source_turn_ids",
    "当前上下文",
    "女生最后一句",
    "男生原回复",
    "原回复评价",
    "聊天阶段",
    "接触状态",
    "关系推进目标",
    "女生状态",
    "男生目标",
    "推荐策略",
    "风险类型",
    "回复强度",
    "高热度信号",
    "次要标签",
    "更优回复",
    "迁移学习价值",
]

TRANSFER_VALUE_KEYWORDS = ["迁移", "学习", "价值", "复用", "可复用", "借鉴", "值得"]
DEFAULT_HEAT_SIGNAL_VALUES = ["无", "亲密称呼", "暧昧试探", "性张力玩笑", "身体接触意象", "关系想象", "线下亲密伏笔", "亲密升级信号", "性关系意向"]
HEAT_SIGNAL_VALUES = DEFAULT_HEAT_SIGNAL_VALUES


def taxonomy() -> dict[str, list[str]]:
    labels = load_config("taxonomy_v01.json").get("labels", {})
    return labels if isinstance(labels, dict) else {}


def aliases() -> dict[str, dict[str, str]]:
    raw = load_config("taxonomy_v01.json").get("aliases", {})
    if not isinstance(raw, dict):
        return {}
    output: dict[str, dict[str, str]] = {}
    for field, values in raw.items():
        if isinstance(values, dict):
            output[str(field)] = {str(key): str(value) for key, value in values.items()}
    return output


def heat_signal_values() -> list[str]:
    values = load_config("taxonomy_v01.json").get("heat_signals", DEFAULT_HEAT_SIGNAL_VALUES)
    if not isinstance(values, list):
        return DEFAULT_HEAT_SIGNAL_VALUES
    cleaned = [str(item) for item in values if str(item)]
    return cleaned or DEFAULT_HEAT_SIGNAL_VALUES


def normalize_label_value(field: str, value: Any, allowed: list[str] | None = None) -> Any:
    allowed = allowed if allowed is not None else taxonomy().get(field, [])
    text = str(value or "").strip()
    text = aliases().get(field, {}).get(text, text)
    return text if text in allowed else allowed[0] if allowed else ""


def normalize_heat_signal(value: Any) -> str:
    allowed = heat_signal_values()
    text = str(value or "").strip()
    text = aliases().get("高热度信号", {}).get(text, text)
    return text if text in allowed else "无"


def normalize_segment(segment: dict[str, Any], case_id: str, index: int) -> dict[str, Any]:
    labels = taxonomy()
    output = {field: segment.get(field, "") for field in SEGMENT_FIELDS}
    output["case_id"] = str(output.get("case_id") or case_id)
    output["schema_version"] = "segments_v01"
    raw_segment_id = str(output.get("segment_id") or f"seg_{index:03d}").strip()
    output["segment_id"] = raw_segment_id if raw_segment_id.startswith(f"{case_id}_") else f"{case_id}_{raw_segment_id}"
    if not isinstance(output.get("source_turn_ids"), list):
        output["source_turn_ids"] = []
    risks = output.get("风险类型")
    if isinstance(risks, str):
        output["风险类型"] = [risks] if risks else []
    elif not isinstance(risks, list):
        output["风险类型"] = []
    for field, allowed in labels.items():
        if field == "风险类型":
            output[field] = [item for item in output.get(field, []) if item in allowed]
            continue
        output[field] = normalize_label_value(field, output.get(field), allowed)
    output["高热度信号"] = normalize_heat_signal(output.get("高热度信号"))
    output["次要标签"] = normalize_secondary_labels(segment.get("次要标签", {}), labels)
    output["quality_status"] = str(segment.get("quality_status") or "draft")
    output["need_human_review"] = bool(segment.get("need_human_review", False))
    output["quality_reason"] = str(segment.get("quality_reason") or "")
    if not str(output.get("迁移学习价值", "")).strip():
        output["迁移学习价值"] = extract_transfer_value(output["quality_reason"])
    return output


def extract_transfer_value(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    pieces = [item.strip() for item in re.split(r"[。！？!?；;\n]+", value) if item.strip()]
    for piece in pieces:
        if any(keyword in piece for keyword in TRANSFER_VALUE_KEYWORDS):
            return piece
    return ""


def normalize_secondary_labels(value: Any, labels: dict[str, list[str]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    output: dict[str, Any] = {}
    for field, allowed in labels.items():
        current = value.get(field, [] if field == "风险类型" else "")
        if field == "风险类型":
            if isinstance(current, str):
                current = [current] if current else []
            if not isinstance(current, list):
                current = []
            output[field] = [item for item in current if item in allowed]
            continue
        output[field] = normalize_label_value(field, current, allowed) if current else ""
    output["说明"] = str(value.get("说明") or value.get("reason") or "")
    return output


def validate_segments(segments: list[dict[str, Any]]) -> list[dict[str, str]]:
    labels = taxonomy()
    issues: list[dict[str, str]] = []
    for segment in segments:
        segment_id = str(segment.get("segment_id", ""))
        for field in SEGMENT_FIELDS:
            if field not in segment:
                issues.append({"segment_id": segment_id, "field": field, "reason": "missing_field"})
        for field, allowed in labels.items():
            if field == "风险类型":
                invalid = [item for item in segment.get(field, []) if item not in allowed]
                if invalid:
                    issues.append({"segment_id": segment_id, "field": field, "reason": f"invalid: {invalid}"})
                continue
            if segment.get(field) not in allowed:
                issues.append({"segment_id": segment_id, "field": field, "reason": f"invalid: {segment.get(field)}"})
        secondary = segment.get("次要标签", {})
        if secondary and not isinstance(secondary, dict):
            issues.append({"segment_id": segment_id, "field": "次要标签", "reason": "invalid_type"})
        if segment.get("高热度信号") not in heat_signal_values():
            issues.append({"segment_id": segment_id, "field": "高热度信号", "reason": f"invalid: {segment.get('高热度信号')}"})
    return issues
