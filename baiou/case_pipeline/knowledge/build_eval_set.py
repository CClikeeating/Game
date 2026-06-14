from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any

from baiou.common.project import baiou_output_root, read_jsonl, write_json, write_jsonl


CHAT_STAGE = "\u804a\u5929\u9636\u6bb5"
GOAL = "\u5173\u7cfb\u63a8\u8fdb\u76ee\u6807"
STRATEGY = "\u63a8\u8350\u7b56\u7565"
REPLY_STRENGTH = "\u56de\u590d\u5f3a\u5ea6"
HEAT_SIGNAL = "\u9ad8\u70ed\u5ea6\u4fe1\u53f7"
TRANSFER_VALUE = "\u8fc1\u79fb\u5b66\u4e60\u4ef7\u503c"
CONTEXT = "\u5f53\u524d\u4e0a\u4e0b\u6587"
FEMALE_LAST = "\u5973\u751f\u6700\u540e\u4e00\u53e5"
MALE_REPLY = "\u7537\u751f\u539f\u56de\u590d"
REPLY_REVIEW = "\u539f\u56de\u590d\u8bc4\u4ef7"
BETTER_REPLY = "\u66f4\u4f18\u56de\u590d"


def build_eval_set(
    batch_id: str,
    output_name: str,
    count: int = 35,
    min_weak: int = 8,
    current_segments: str | Path | None = None,
    audit_json: str | Path | None = None,
    output_root: str | Path | None = None,
    copy_markdown: bool = True,
) -> dict[str, Any]:
    current_path = Path(current_segments) if current_segments else baiou_output_root() / "cases" / "knowledge" / "current" / "segments.jsonl"
    rows = [row for row in read_jsonl(current_path) if row_belongs_to_batch(row, batch_id)]
    if not rows:
        raise ValueError(f"No current rows found for batch_id={batch_id}")
    weak_turn_ids = load_weak_turn_ids(audit_json)
    for row in rows:
        row["_eval_is_weak_ack"] = is_weak_row(row, weak_turn_ids)

    selected = select_rows(rows, count, min_weak)
    weak_count = sum(1 for row in selected if row.get("_eval_is_weak_ack"))
    if weak_count < min_weak:
        raise ValueError(f"Only selected {weak_count} weak rows, expected at least {min_weak}.")

    root = Path(output_root) if output_root else baiou_output_root() / "cases" / "knowledge" / "eval_sets"
    target = root / output_name
    target.mkdir(parents=True, exist_ok=True)
    clean_rows = [clean_eval_row(row, index) for index, row in enumerate(selected, start=1)]
    copied = copy_markdown_files(current_path.parent, target, clean_rows) if copy_markdown else []
    write_jsonl(target / "segments.jsonl", clean_rows)
    write_csv(target / "segments.csv", clean_rows)
    write_upload_manifest(target / "upload_manifest.csv", clean_rows)
    summary = {
        "schema_version": "segment_eval_set_v01",
        "batch_id": batch_id,
        "output_name": output_name,
        "count": len(clean_rows),
        "min_weak": min_weak,
        "weak_count": weak_count,
        "source_current_segments": str(current_path),
        "output_dir": str(target),
        "copied_markdown_count": len(copied),
        "segments_jsonl": str(target / "segments.jsonl"),
        "segments_csv": str(target / "segments.csv"),
        "upload_manifest": str(target / "upload_manifest.csv"),
        "markdown_dir": str(target / "md") if copy_markdown else "",
    }
    write_json(target / "eval_set_summary.json", summary)
    return summary


def row_belongs_to_batch(row: dict[str, Any], batch_id: str) -> bool:
    return batch_id in str(row.get("rag_import_folder", "")) or batch_id in str(row.get("rag_file_path", ""))


def load_weak_turn_ids(audit_json: str | Path | None) -> set[tuple[str, str]]:
    if not audit_json:
        return set()
    payload = json.loads(Path(audit_json).read_text(encoding="utf-8"))
    output: set[tuple[str, str]] = set()
    for batch in payload.get("batches", []) if isinstance(payload.get("batches"), list) else []:
        for case in batch.get("cases", []) if isinstance(batch.get("cases"), list) else []:
            case_id = str(case.get("case_id", ""))
            for turn in case.get("weak_turns", []) if isinstance(case.get("weak_turns"), list) else []:
                turn_id = str(turn.get("turn_id", ""))
                if case_id and turn_id:
                    output.add((case_id, turn_id))
    return output


def is_weak_row(row: dict[str, Any], weak_turn_ids: set[tuple[str, str]]) -> bool:
    case_id = str(row.get("case_id", ""))
    source_ids = {str(item) for item in row.get("source_turn_ids", []) if str(item)}
    if any((case_id, turn_id) in weak_turn_ids for turn_id in source_ids):
        return True
    text = "\n".join(
        str(row.get(field, ""))
        for field in [CONTEXT, FEMALE_LAST, MALE_REPLY, REPLY_REVIEW, BETTER_REPLY, TRANSFER_VALUE, "search_text"]
    )
    return any(term in text for term in ["\u5f31\u627f\u63a5", "\u4f4e\u538b\u529b", "\u81ea\u7136\u6536\u5c3e"])


def select_rows(rows: list[dict[str, Any]], count: int, min_weak: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    case_counts: dict[str, int] = {}

    weak_candidates = sorted([row for row in rows if row.get("_eval_is_weak_ack")], key=weak_score)
    add_diverse(selected, seen_ids, case_counts, weak_candidates, min_weak, max_per_case=2)

    buckets = [
        lambda row: label(row, STRATEGY) in {"\u4e3b\u52a8\u964d\u538b", "\u5171\u60c5\u56de\u5e94", "\u8bdd\u9898\u5ef6\u5c55"},
        lambda row: label(row, GOAL) == "\u9080\u7ea6\u89c1\u9762",
        lambda row: str(row.get(HEAT_SIGNAL, "")) not in {"", "\u65e0"},
        lambda row: label(row, REPLY_STRENGTH) in {"\u5b89\u5168", "\u8f7b\u677e"},
        lambda row: "supp_missing" in str(row.get("segment_id", "")),
    ]
    while len(selected) < count:
        grew = False
        for predicate in buckets:
            if len(selected) >= count:
                break
            candidates = [row for row in rows if predicate(row) and row_id(row) not in seen_ids]
            before = len(selected)
            add_diverse(selected, seen_ids, case_counts, sorted(candidates, key=general_score), 1, max_per_case=2)
            grew = grew or len(selected) > before
        if not grew:
            remaining = [row for row in rows if row_id(row) not in seen_ids]
            add_diverse(selected, seen_ids, case_counts, sorted(remaining, key=general_score), count - len(selected), max_per_case=3)
        if not grew and not [row for row in rows if row_id(row) not in seen_ids]:
            break
    return selected[:count]


def add_diverse(
    selected: list[dict[str, Any]],
    seen_ids: set[str],
    case_counts: dict[str, int],
    candidates: list[dict[str, Any]],
    limit: int,
    max_per_case: int,
) -> None:
    added = 0
    for row in candidates:
        if added >= limit:
            return
        segment_id = row_id(row)
        case_id = str(row.get("case_id", ""))
        if segment_id in seen_ids or case_counts.get(case_id, 0) >= max_per_case:
            continue
        selected.append(row)
        seen_ids.add(segment_id)
        case_counts[case_id] = case_counts.get(case_id, 0) + 1
        added += 1


def weak_score(row: dict[str, Any]) -> tuple[int, str, str]:
    heat = 0 if str(row.get(HEAT_SIGNAL, "")) in {"", "\u65e0"} else 1
    strategy = 0 if label(row, STRATEGY) in {"\u4e3b\u52a8\u964d\u538b", "\u5171\u60c5\u56de\u5e94", "\u8bdd\u9898\u5ef6\u5c55"} else 1
    supplement = 0 if "supp_missing" in str(row.get("segment_id", "")) else 1
    return (heat + strategy + supplement, str(row.get("case_id", "")), str(row.get("segment_id", "")))


def general_score(row: dict[str, Any]) -> tuple[int, str, str]:
    supplement_penalty = 1 if "supp_missing" in str(row.get("segment_id", "")) else 0
    return (supplement_penalty, str(row.get("case_id", "")), str(row.get("segment_id", "")))


def label(row: dict[str, Any], key: str) -> str:
    labels = row.get("labels", {}) if isinstance(row.get("labels"), dict) else {}
    return str(labels.get(key, ""))


def row_id(row: dict[str, Any]) -> str:
    return str(row.get("segment_id", ""))


def clean_eval_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    output = {key: value for key, value in row.items() if not key.startswith("_")}
    output["eval_index"] = index
    output["eval_is_weak_ack"] = bool(row.get("_eval_is_weak_ack"))
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "eval_index",
        "eval_is_weak_ack",
        "case_id",
        "segment_id",
        "source_turn_ids",
        CHAT_STAGE,
        GOAL,
        STRATEGY,
        REPLY_STRENGTH,
        HEAT_SIGNAL,
        FEMALE_LAST,
        MALE_REPLY,
        REPLY_REVIEW,
        BETTER_REPLY,
        TRANSFER_VALUE,
        "rag_file_path",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_row(row, fields))


def csv_row(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    output = {field: row.get(field, "") for field in fields}
    labels = row.get("labels", {}) if isinstance(row.get("labels"), dict) else {}
    for field in [CHAT_STAGE, GOAL, STRATEGY, REPLY_STRENGTH]:
        output[field] = labels.get(field, "")
    output["source_turn_ids"] = ", ".join(str(item) for item in row.get("source_turn_ids", []))
    return output


def write_upload_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["eval_index", "case_id", "segment_id", "file_path", "upload_status", "notes"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "eval_index": row.get("eval_index", ""),
                    "case_id": row.get("case_id", ""),
                    "segment_id": row.get("segment_id", ""),
                    "file_path": row.get("eval_md_path", row.get("rag_file_path", "")),
                    "upload_status": "pending",
                    "notes": "weak_ack" if row.get("eval_is_weak_ack") else "",
                }
            )


def copy_markdown_files(current_root: Path, target: Path, rows: list[dict[str, Any]]) -> list[str]:
    rag_root = current_root / "rag_knowledge_base"
    md_root = target / "md"
    md_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for row in rows:
        relative = str(row.get("rag_file_path", "")).strip()
        if not relative:
            continue
        source = rag_root / relative
        if not source.exists():
            continue
        dest = md_root / source.name
        shutil.copy2(source, dest)
        row["eval_md_path"] = f"md/{dest.name}"
        copied.append(str(dest))
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fixed product regression eval set from current segment assets.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--count", type=int, default=35)
    parser.add_argument("--min-weak", type=int, default=8)
    parser.add_argument("--current-segments")
    parser.add_argument("--audit-json")
    parser.add_argument("--output-root")
    parser.add_argument("--no-copy-markdown", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            build_eval_set(
                batch_id=args.batch_id,
                output_name=args.output_name,
                count=args.count,
                min_weak=args.min_weak,
                current_segments=args.current_segments,
                audit_json=args.audit_json,
                output_root=args.output_root,
                copy_markdown=not args.no_copy_markdown,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
