from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from baiou.common.io import PROJECT_ROOT
from baiou.case_pipeline.common import load_config, read_jsonl


def search_segments(query: str, labels: dict[str, Any] | None = None, index_path: str | None = None, top_k: int | None = None) -> list[dict[str, Any]]:
    config = load_config("retrieval.json")
    path = Path(index_path or config.get("default_index", "outputs/baiou/cases/knowledge/current/local_index/segments_index.jsonl"))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    rows = read_jsonl(path)
    labels = labels or {}
    top_k = top_k or int(config.get("top_k", 3))
    min_score = int(config.get("min_score", 1))
    weights = config.get("weights", {}) if isinstance(config.get("weights"), dict) else {}
    scored = []
    for row in rows:
        score, reasons = score_row(query, labels, row, weights)
        if score >= min_score:
            enriched = dict(row)
            enriched["score"] = score
            enriched["match_reasons"] = reasons
            scored.append(enriched)
    scored.sort(key=lambda item: item.get("score", 0), reverse=True)
    return scored[:top_k]


def score_row(query: str, labels: dict[str, Any], row: dict[str, Any], weights: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    row_labels = row.get("labels", {}) if isinstance(row.get("labels"), dict) else {}
    secondary_labels = row.get("secondary_labels", {}) if isinstance(row.get("secondary_labels"), dict) else {}
    for field in ["聊天阶段", "接触状态", "关系推进目标", "女生状态", "男生目标", "推荐策略", "回复强度"]:
        if labels.get(field) and labels.get(field) == row_labels.get(field):
            value = int(weights.get(field, 1))
            score += value
            reasons.append(f"{field}匹配")
        elif labels.get(field) and labels.get(field) == secondary_labels.get(field):
            value = max(1, int(weights.get(field, 1)) // 2)
            score += value
            reasons.append(f"{field}次要匹配")
    if labels.get("高热度信号") and labels.get("高热度信号") == row.get("高热度信号"):
        score += int(weights.get("高热度信号", 3))
        reasons.append("高热度信号匹配")
    query_risks = labels.get("风险类型", []) if isinstance(labels.get("风险类型", []), list) else []
    row_risks = row_labels.get("风险类型", []) if isinstance(row_labels.get("风险类型", []), list) else []
    overlap = [risk for risk in query_risks if risk in row_risks]
    if overlap:
        score += int(weights.get("风险类型", 1)) * len(overlap)
        reasons.append("风险类型匹配:" + ",".join(overlap))
    secondary_risks = secondary_labels.get("风险类型", []) if isinstance(secondary_labels.get("风险类型", []), list) else []
    secondary_overlap = [risk for risk in query_risks if risk in secondary_risks and risk not in overlap]
    if secondary_overlap:
        score += max(1, int(weights.get("风险类型", 1)) // 2) * len(secondary_overlap)
        reasons.append("风险类型次要匹配:" + ",".join(secondary_overlap))
    haystack = json.dumps(row, ensure_ascii=False)
    for token in extract_tokens(query):
        if token and token in haystack:
            score += int(weights.get("token", 1))
            reasons.append(f"文本命中:{token}")
    return score, reasons


def extract_tokens(text: str) -> list[str]:
    raw = [item.strip(" ，。！？,.!?;；:：\n\t") for item in re.split(r"\s+", text)]
    tokens = [item for item in raw if len(item) >= 2]
    fixed = [
        "哈哈",
        "在干嘛",
        "忙",
        "不回",
        "冷淡",
        "拒绝",
        "邀约",
        "见面",
        "吃饭",
        "电影",
        "工作",
        "朋友圈",
        "表情",
        "怎么回",
        "下班",
        "接我",
        "接我下班",
        "网红",
        "异地",
        "圣诞",
        "礼物",
    ]
    tokens.extend(token for token in fixed if token in text)
    compact = re.sub(r"\s+", "", text)
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{4,}", compact)
    for run in cjk_runs:
        for size in (2, 3, 4):
            for index in range(0, max(0, len(run) - size + 1)):
                tokens.append(run[index : index + size])
                if len(tokens) >= 120:
                    return list(dict.fromkeys(tokens))
    return list(dict.fromkeys(tokens))


def main() -> None:
    parser = argparse.ArgumentParser(description="Search local Baiou segment index.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--labels-json", default="{}")
    parser.add_argument("--index-path")
    parser.add_argument("--top-k", type=int)
    args = parser.parse_args()
    labels = json.loads(args.labels_json)
    print(json.dumps(search_segments(args.query, labels, args.index_path, args.top_k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
