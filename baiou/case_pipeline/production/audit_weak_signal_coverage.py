from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from baiou.case_pipeline.common import OUTPUT_ROOT
from baiou.common.io import PROJECT_ROOT, read_json, write_json

DEFAULT_WEAK_ACKS = [
    "嗯",
    "嗯嗯",
    "好",
    "好的",
    "知道啦",
    "知道了",
    "行",
    "收到",
    "嗯呢",
    "嗯呐",
    "好吧",
    "好呀",
    "可以",
    "OK",
    "ok",
    "哈哈",
    "哈哈哈",
    "哦",
    "噢",
]
DEFAULT_WEAK_SUBSTRINGS = ["嗯嗯", "嗯好", "好的", "知道啦", "知道了", "收到", "好吧", "好呀", "行吧"]
LABEL_FIELDS = ["聊天阶段", "关系推进目标", "女生状态", "男生目标", "推荐策略", "回复强度", "高热度信号"]
FOCUS_REVIEW_FIELDS = ["聊天阶段", "关系推进目标", "高热度信号", "女生状态"]


def load_source_cases(source_bundle: str | Path) -> dict[str, dict[str, Any]]:
    path = resolve_path(source_bundle)
    if path.is_dir():
        path = path / "batch_chat_turns.json"
    payload = read_json(path)
    return {str(case.get("case_id", "")): case for case in payload.get("cases", []) if isinstance(case, dict)}


def audit_batches(
    source_bundle: str | Path,
    batch_ids: list[str],
    segments_root: str | Path | None = None,
    weak_acks: list[str] | None = None,
    weak_substrings: list[str] | None = None,
) -> dict[str, Any]:
    cases = load_source_cases(source_bundle)
    roots = [audit_batch(batch_id, cases, segments_root, weak_acks, weak_substrings) for batch_id in batch_ids]
    return {
        "schema_version": "weak_signal_coverage_audit_v01",
        "source_bundle": str(source_bundle),
        "batch_count": len(roots),
        "batches": roots,
    }


def audit_batch(
    batch_id: str,
    source_cases: dict[str, dict[str, Any]],
    segments_root: str | Path | None = None,
    weak_acks: list[str] | None = None,
    weak_substrings: list[str] | None = None,
) -> dict[str, Any]:
    batch_root = resolve_segments_root(segments_root) / batch_id
    manifest = read_json(batch_root / "segments_manifest.json")
    weak_terms = weak_acks or DEFAULT_WEAK_ACKS
    weak_parts = weak_substrings or DEFAULT_WEAK_SUBSTRINGS
    cases: list[dict[str, Any]] = []
    label_counts = {field: Counter() for field in LABEL_FIELDS}
    review_issue_counts = Counter()
    review_verdict_counts = Counter()
    totals = Counter()
    for row in manifest.get("cases", []):
        case_id = str(row.get("case_id", ""))
        case_dir = resolve_case_dir(batch_root, row)
        source_case = source_cases.get(case_id, {})
        case_audit = audit_case(case_id, source_case, case_dir, weak_terms, weak_parts)
        cases.append(case_audit)
        totals["weak_turn_count"] += case_audit["weak_turn_count"]
        totals["primary_covered_count"] += case_audit["primary_covered_count"]
        totals["final_covered_count"] += case_audit["final_covered_count"]
        totals["weak_missing_turn_count"] += case_audit["weak_missing_turn_count"]
        totals["weak_actionable_count"] += case_audit["weak_actionable_count"]
        totals["segment_count"] += case_audit["segment_count"]
        totals["missing_node_count"] += case_audit["missing_node_count"]
        totals["weak_missing_node_count"] += case_audit["weak_missing_node_count"]
        totals["review_focus_issue_count"] += case_audit["review_focus_issue_count"]
        for field, counts in case_audit["label_counts"].items():
            label_counts[field].update(counts)
        review_issue_counts.update(case_audit["review_issue_counts"])
        review_verdict_counts.update(case_audit["review_verdict_counts"])
    return {
        "batch_id": batch_id,
        "batch_root": str(batch_root),
        "case_count": len(cases),
        "segment_count": totals["segment_count"],
        "weak_turn_count": totals["weak_turn_count"],
        "primary_covered_count": totals["primary_covered_count"],
        "final_covered_count": totals["final_covered_count"],
        "weak_missing_turn_count": totals["weak_missing_turn_count"],
        "weak_actionable_count": totals["weak_actionable_count"],
        "missing_node_count": totals["missing_node_count"],
        "weak_missing_node_count": totals["weak_missing_node_count"],
        "review_focus_issue_count": totals["review_focus_issue_count"],
        "review_issue_counts": dict(review_issue_counts.most_common()),
        "review_verdict_counts": dict(review_verdict_counts.most_common()),
        "label_counts": stringify_counters(label_counts),
        "cases": cases,
    }


def audit_case(
    case_id: str,
    source_case: dict[str, Any],
    case_dir: Path,
    weak_acks: list[str],
    weak_substrings: list[str],
) -> dict[str, Any]:
    weak_turns = find_weak_turns(source_case, weak_acks, weak_substrings)
    primary_segments = load_primary_segments(case_dir)
    final_segments = load_final_segments(case_dir)
    primary_coverage = coverage_by_turn(primary_segments)
    final_coverage = coverage_by_turn(final_segments)
    review_segments = load_review_segments(case_dir)
    missing_nodes = load_missing_nodes(case_dir)
    weak_ids = {turn["turn_id"] for turn in weak_turns}
    weak_missing_turn_ids = missing_weak_turn_ids(missing_nodes, weak_ids)
    final_covered_ids = {turn_id for turn_id in weak_ids if turn_id in final_coverage}
    weak_actionable_ids = final_covered_ids | weak_missing_turn_ids
    missing_coverage = missing_nodes_by_turn(missing_nodes)
    label_counts = label_distribution(final_segments)
    review_issue_counts = review_issue_distribution(review_segments)
    review_verdict_counts = review_verdict_distribution(review_segments)
    return {
        "case_id": case_id,
        "case_dir": str(case_dir),
        "segment_count": len(final_segments),
        "weak_turn_count": len(weak_turns),
        "primary_covered_count": sum(1 for turn_id in weak_ids if turn_id in primary_coverage),
        "final_covered_count": len(final_covered_ids),
        "weak_missing_turn_count": len(weak_missing_turn_ids),
        "weak_actionable_count": len(weak_actionable_ids),
        "missing_node_count": len(missing_nodes),
        "weak_missing_node_count": count_weak_missing_nodes(missing_nodes, weak_ids),
        "label_counts": stringify_counters(label_counts),
        "review_focus_issue_count": sum(review_issue_counts.get(field, 0) for field in FOCUS_REVIEW_FIELDS),
        "review_issue_counts": dict(review_issue_counts.most_common()),
        "review_verdict_counts": dict(review_verdict_counts.most_common()),
        "weak_turns": [
            {
                **turn,
                "primary_segments": primary_coverage.get(turn["turn_id"], []),
                "final_segments": final_coverage.get(turn["turn_id"], []),
                "missing_nodes": missing_coverage.get(turn["turn_id"], []),
                "actionable": turn["turn_id"] in weak_actionable_ids,
            }
            for turn in weak_turns
        ],
    }


def find_weak_turns(source_case: dict[str, Any], weak_acks: list[str], weak_substrings: list[str]) -> list[dict[str, Any]]:
    turns = flatten_turns(source_case)
    output: list[dict[str, Any]] = []
    exact = {normalize_text(item) for item in weak_acks if normalize_text(item)}
    for index, turn in enumerate(turns):
        if turn.get("speaker") != "female":
            continue
        text = str(turn.get("text", "") or "").strip()
        normalized = normalize_text(text)
        if not is_weak_ack_text(text, exact, weak_substrings):
            continue
        previous_male = [item for item in turns[max(0, index - 3) : index] if item.get("speaker") == "male"][-2:]
        next_male = [item for item in turns[index + 1 : index + 4] if item.get("speaker") == "male"][:2]
        output.append(
            {
                "turn_id": str(turn.get("turn_id", "")),
                "text": text,
                "previous_male": compact_turns(previous_male),
                "next_male": compact_turns(next_male),
            }
        )
    return output


def load_primary_segments(case_dir: Path) -> list[dict[str, Any]]:
    path = case_dir / "primary_result.json"
    if not path.exists():
        return []
    parsed = read_json(path).get("parsed", {})
    segments = parsed.get("segments", []) if isinstance(parsed, dict) else []
    return [item for item in segments if isinstance(item, dict)] if isinstance(segments, list) else []


def load_final_segments(case_dir: Path) -> list[dict[str, Any]]:
    path = case_dir / "segments.json"
    if not path.exists():
        return []
    segments = read_json(path).get("segments", [])
    return [item for item in segments if isinstance(item, dict)] if isinstance(segments, list) else []


def load_missing_nodes(case_dir: Path) -> list[dict[str, Any]]:
    path = case_dir / "review_result.json"
    if not path.exists():
        return []
    parsed = read_json(path).get("parsed", {})
    nodes = parsed.get("missing_nodes", []) if isinstance(parsed, dict) else []
    return [item for item in nodes if isinstance(item, dict)] if isinstance(nodes, list) else []


def load_review_segments(case_dir: Path) -> list[dict[str, Any]]:
    path = case_dir / "review_result.json"
    if not path.exists():
        return []
    parsed = read_json(path).get("parsed", {})
    reviews = parsed.get("segment_reviews", []) if isinstance(parsed, dict) else []
    return [item for item in reviews if isinstance(item, dict)] if isinstance(reviews, list) else []


def coverage_by_turn(segments: list[dict[str, Any]]) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = defaultdict(list)
    for segment in segments:
        segment_id = str(segment.get("segment_id", ""))
        for turn_id in segment.get("source_turn_ids", []) if isinstance(segment.get("source_turn_ids", []), list) else []:
            if str(turn_id):
                coverage[str(turn_id)].append(segment_id)
    return dict(coverage)


def label_distribution(segments: list[dict[str, Any]]) -> dict[str, Counter]:
    output = {field: Counter() for field in LABEL_FIELDS}
    for segment in segments:
        labels = segment.get("labels", {}) if isinstance(segment.get("labels", {}), dict) else {}
        for field in LABEL_FIELDS:
            value = segment.get(field, labels.get(field, ""))
            output[field][str(value or "")] += 1
    return output


def review_issue_distribution(reviews: list[dict[str, Any]]) -> Counter:
    output = Counter()
    for review in reviews:
        for issue in review.get("issues", []) if isinstance(review.get("issues", []), list) else []:
            if not isinstance(issue, dict):
                continue
            field = str(issue.get("field", "")).strip()
            output[field.split(".", 1)[0] if "." in field else field] += 1
    return output


def review_verdict_distribution(reviews: list[dict[str, Any]]) -> Counter:
    output = Counter()
    for review in reviews:
        verdict = str(review.get("verdict", "") or "").strip().lower()
        if verdict:
            output[verdict] += 1
    return output


def count_weak_missing_nodes(missing_nodes: list[dict[str, Any]], weak_ids: set[str]) -> int:
    count = 0
    keywords = ["弱承接", "低信息", "自然收尾", "低压力", "嗯嗯", "好的", "收到", "好吧"]
    for node in missing_nodes:
        source_ids = {str(item) for item in node.get("source_turn_ids", []) if str(item)}
        text = json.dumps(node, ensure_ascii=False)
        if source_ids & weak_ids or any(keyword in text for keyword in keywords):
            count += 1
    return count


def missing_weak_turn_ids(missing_nodes: list[dict[str, Any]], weak_ids: set[str]) -> set[str]:
    output: set[str] = set()
    for node in missing_nodes:
        source_ids = {str(item) for item in node.get("source_turn_ids", []) if str(item)}
        output.update(source_ids & weak_ids)
    return output


def missing_nodes_by_turn(missing_nodes: list[dict[str, Any]]) -> dict[str, list[int]]:
    output: dict[str, list[int]] = defaultdict(list)
    for index, node in enumerate(missing_nodes, start=1):
        for turn_id in node.get("source_turn_ids", []) if isinstance(node.get("source_turn_ids", []), list) else []:
            if str(turn_id):
                output[str(turn_id)].append(index)
    return dict(output)


def is_weak_ack_text(text: str, exact: set[str], weak_prefixes: list[str]) -> bool:
    normalized = normalize_text(text)
    lead = re.sub(r"^(哈)+", "", normalized).lstrip("那啊呀额哦噢")
    if normalized in exact or lead in exact:
        return True
    prefixes = [normalize_text(item) for item in weak_prefixes if normalize_text(item)]
    return any(lead.startswith(prefix) for prefix in prefixes)


def flatten_turns(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        turn
        for block in case.get("blocks", []) if isinstance(case.get("blocks", []), list)
        for turn in block.get("turns", []) if isinstance(block.get("turns", []), list)
        if isinstance(turn, dict)
    ]


def compact_turns(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"turn_id": str(turn.get("turn_id", "")), "text": str(turn.get("text", "") or "")} for turn in turns]


def normalize_text(text: str) -> str:
    return re.sub(r"[\s，。！？!?,.;；:：~～…（）()\[\]【】\"“”]+", "", str(text or "").strip())


def stringify_counters(value: dict[str, Counter]) -> dict[str, dict[str, int]]:
    return {field: dict(counter.most_common()) for field, counter in value.items()}


def resolve_segments_root(segments_root: str | Path | None) -> Path:
    if segments_root:
        return resolve_path(segments_root)
    return OUTPUT_ROOT / "segments"


def resolve_case_dir(batch_root: Path, row: dict[str, Any]) -> Path:
    text = str(row.get("case_dir", "")).strip()
    case_id = str(row.get("case_id", "")).strip()
    path = Path(text) if text else batch_root / "cases" / case_id
    return path if path.is_absolute() else batch_root / path


def resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit weak acknowledgement coverage in Baiou case segment batches.")
    parser.add_argument("--source-bundle", required=True, help="Source bundle directory or batch_chat_turns.json.")
    parser.add_argument("--batch-id", action="append", required=True, help="Segment batch id. Repeat for A/B comparisons.")
    parser.add_argument("--segments-root", help="Optional root containing segment batch directories.")
    parser.add_argument("--weak-ack", action="append", help="Additional exact weak acknowledgement phrase.")
    parser.add_argument("--weak-substring", action="append", help="Additional weak acknowledgement substring.")
    parser.add_argument("--output-json", help="Optional path to write the audit JSON.")
    args = parser.parse_args()
    weak_acks = DEFAULT_WEAK_ACKS + (args.weak_ack or [])
    weak_substrings = DEFAULT_WEAK_SUBSTRINGS + (args.weak_substring or [])
    result = audit_batches(args.source_bundle, args.batch_id, args.segments_root, weak_acks, weak_substrings)
    if args.output_json:
        write_json(args.output_json, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
