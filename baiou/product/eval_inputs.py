from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from baiou.common.io import PROJECT_ROOT, resolve_path, write_jsonl
from baiou.common.project import read_jsonl


TURN_RE = re.compile(r"^\s*(?P<focus>\*)?\s*(?P<turn_id>turn_\d+)\s+(?P<speaker>男生|女生):\s*(?P<text>.*)$")

FIELD_CONTEXT = "当前上下文"
FIELD_FEMALE_LAST = "女生最后一句"
FIELD_MALE_ORIGINAL = "男生原回复"
FIELD_BETTER_REPLY = "更优回复"
FIELD_TRANSFER_VALUE = "迁移学习价值"
FIELD_HEAT_SIGNAL = "高热度信号"


def parse_turns(context: str) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for line in str(context or "").splitlines():
        match = TURN_RE.match(line)
        if not match:
            continue
        turns.append(
            {
                "turn_id": match.group("turn_id"),
                "speaker": match.group("speaker"),
                "text": match.group("text").strip(),
                "raw": f"{match.group('turn_id')} {match.group('speaker')}: {match.group('text').strip()}",
                "focused": "true" if match.group("focus") else "false",
            }
        )
    return turns


def expected_reply_from_row(row: dict[str, Any]) -> tuple[str, str]:
    better = str(row.get(FIELD_BETTER_REPLY, "") or "").strip()
    original = str(row.get(FIELD_MALE_ORIGINAL, "") or "").strip()
    extracted = extract_preserved_reply(better)
    if extracted:
        return extracted, "better_reply_preserved_quote"
    if better and not better.startswith("保留原回复"):
        return better, "better_reply"
    return original, "male_original_reply"


def extract_preserved_reply(text: str) -> str:
    for left, right in [("“", "”"), ('"', '"'), ("「", "」")]:
        if left in text and right in text:
            start = text.find(left) + len(left)
            end = text.find(right, start)
            if end > start:
                return text[start:end].strip()
    return ""


def build_eval_input(row: dict[str, Any]) -> dict[str, Any]:
    turns = parse_turns(str(row.get(FIELD_CONTEXT, "") or ""))
    relevant_turns, turn_selection = select_relevant_turns(row, turns)
    last_turn = relevant_turns[-1] if relevant_turns else {}
    last_speaker = last_turn.get("speaker", "")
    input_turns = turns_through(turns, last_turn)
    expected_reply, expected_source = expected_reply_from_row(row)

    if last_speaker == "男生":
        reply_turns = trailing_speaker_block(relevant_turns, "男生")
        input_turns = turns_before(turns, reply_turns[0] if reply_turns else last_turn)
        expected_reply = "\n".join(turn.get("text", "").strip() for turn in reply_turns if turn.get("text", "").strip())
        expected_source = "last_male_turn_block"

    female_prompt = latest_speaker_text(input_turns, "女生") or str(row.get(FIELD_FEMALE_LAST, "") or "").strip()
    context = "\n".join(turn["raw"] for turn in input_turns)
    labels = row.get("labels", {}) if isinstance(row.get("labels", {}), dict) else {}
    issues = eval_input_issues(female_prompt, expected_reply)
    return {
        "schema_version": "baiou_product_eval_input_v01",
        "eval_index": row.get("eval_index", ""),
        "eval_is_weak_ack": bool(row.get("eval_is_weak_ack", False)),
        "case_id": row.get("case_id", ""),
        "segment_id": row.get("segment_id", ""),
        "question": "我该怎么回？",
        "context": context,
        "female_prompt": female_prompt,
        "expected_reply": expected_reply,
        "expected_reply_source": expected_source,
        "expected_reply_optional": False,
        "expected_reply_turn_ids": [turn.get("turn_id", "") for turn in reply_turns] if last_speaker == "男生" else [],
        "eval_input_ready": not issues,
        "eval_input_issues": issues,
        "turn_selection": turn_selection,
        "last_visible_speaker": input_turns[-1].get("speaker", "") if input_turns else "",
        "original_last_speaker": last_speaker,
        "original_last_text": last_turn.get("text", ""),
        "labels": labels,
        "heat_signal": row.get(FIELD_HEAT_SIGNAL, ""),
        "transfer_value": row.get(FIELD_TRANSFER_VALUE, ""),
        "source_turn_ids": row.get("source_turn_ids", []),
        "source_rag_file_path": row.get("rag_file_path", ""),
    }


def trailing_speaker_block(turns: list[dict[str, str]], speaker: str) -> list[dict[str, str]]:
    block: list[dict[str, str]] = []
    for turn in reversed(turns):
        if turn.get("speaker") != speaker:
            break
        block.append(turn)
    return list(reversed(block))


def turns_before(turns: list[dict[str, str]], first_removed_turn: dict[str, str]) -> list[dict[str, str]]:
    if not first_removed_turn:
        return turns
    turn_id = first_removed_turn.get("turn_id", "")
    for index, turn in enumerate(turns):
        if turn.get("turn_id") == turn_id:
            return turns[:index]
    return turns


def select_relevant_turns(row: dict[str, Any], turns: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    focused = [turn for turn in turns if turn.get("focused") == "true"]
    if focused:
        return focused, "focused_turns"
    source_turn_ids = {str(turn_id) for turn_id in row.get("source_turn_ids", []) if str(turn_id).strip()}
    if source_turn_ids:
        selected = [turn for turn in turns if turn.get("turn_id") in source_turn_ids]
        if selected:
            return selected, "source_turn_ids"
    return turns, "all_context"


def turns_through(turns: list[dict[str, str]], last_turn: dict[str, str]) -> list[dict[str, str]]:
    if not last_turn:
        return []
    last_id = last_turn.get("turn_id", "")
    for index, turn in enumerate(turns):
        if turn.get("turn_id") == last_id:
            return turns[: index + 1]
    return turns


def eval_input_issues(female_prompt: str, expected_reply: str) -> list[str]:
    issues: list[str] = []
    if not female_prompt:
        issues.append("missing_female_prompt")
    if female_prompt and expected_reply and female_prompt.strip() == expected_reply.strip():
        issues.append("expected_reply_matches_female_prompt")
    return issues


def latest_speaker_text(turns: list[dict[str, str]], speaker: str) -> str:
    for turn in reversed(turns):
        if turn.get("speaker") == speaker:
            return turn.get("text", "").strip()
    return ""


def write_eval_inputs(
    segments_jsonl: str | Path,
    output_dir: str | Path | None = None,
    overrides_path: str | Path | None = None,
) -> dict[str, Any]:
    source = resolve_path(segments_jsonl)
    rows = read_jsonl(source)
    target_dir = resolve_path(output_dir) if output_dir else source.parent
    overrides = load_overrides(overrides_path, target_dir)
    cases = apply_overrides([build_eval_input(row) for row in rows], overrides)
    jsonl_path = target_dir / "product_eval_inputs.jsonl"
    csv_path = target_dir / "product_eval_inputs.csv"
    summary_path = target_dir / "product_eval_inputs_summary.json"

    write_jsonl(jsonl_path, cases)
    write_csv(csv_path, cases)
    summary = {
        "schema_version": "baiou_product_eval_inputs_summary_v01",
        "source_segments_jsonl": str(source),
        "case_count": len(cases),
        "weak_count": sum(1 for case in cases if case.get("eval_is_weak_ack")),
        "ready_count": sum(1 for case in cases if case.get("eval_input_ready")),
        "needs_review_count": sum(1 for case in cases if not case.get("eval_input_ready")),
        "without_expected_reply_count": sum(1 for case in cases if not str(case.get("expected_reply", "")).strip()),
        "last_male_turn_expected_count": sum(1 for case in cases if case.get("expected_reply_source") == "last_male_turn_block"),
        "last_female_prompt_count": sum(1 for case in cases if case.get("original_last_speaker") == "女生"),
        "overrides_file": str(overrides.get("_path", "")),
        "excluded_count": len(overrides.get("exclude_eval_indices", [])),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def load_overrides(overrides_path: str | Path | None, output_dir: Path) -> dict[str, Any]:
    target = resolve_path(overrides_path) if overrides_path else output_dir / "product_eval_overrides.json"
    if not target.exists():
        return {}
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return {}
    data["_path"] = str(target)
    return data


def apply_overrides(cases: list[dict[str, Any]], overrides: dict[str, Any]) -> list[dict[str, Any]]:
    excluded = {str(value) for value in overrides.get("exclude_eval_indices", [])}
    by_index = overrides.get("cases", {}) if isinstance(overrides.get("cases", {}), dict) else {}
    curated: list[dict[str, Any]] = []
    for case in cases:
        eval_index = str(case.get("eval_index", ""))
        if eval_index in excluded:
            continue
        patch = by_index.get(eval_index, {})
        if isinstance(patch, dict):
            case = dict(case)
            case.update(patch)
            if bool(case.get("expected_reply_optional", False)) and not str(case.get("expected_reply", "")).strip():
                case["eval_input_issues"] = [issue for issue in case.get("eval_input_issues", []) if issue != "missing_expected_reply"]
                case["eval_input_ready"] = "missing_female_prompt" not in case.get("eval_input_issues", [])
        curated.append(case)
    return curated


def write_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "eval_index",
        "eval_is_weak_ack",
        "case_id",
        "segment_id",
        "question",
        "female_prompt",
        "expected_reply",
        "expected_reply_source",
        "expected_reply_optional",
        "eval_input_ready",
        "eval_input_issues",
        "turn_selection",
        "last_visible_speaker",
        "original_last_speaker",
        "original_last_text",
        "heat_signal",
        "source_rag_file_path",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow({field: csv_value(case.get(field, "")) for field in fields})


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product-ready eval inputs from Baiou segment eval sets.")
    parser.add_argument("segments_jsonl")
    parser.add_argument("--output-dir")
    parser.add_argument("--overrides-path")
    args = parser.parse_args()
    print(json.dumps(write_eval_inputs(args.segments_jsonl, args.output_dir, args.overrides_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
