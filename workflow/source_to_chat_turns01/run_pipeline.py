from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .config_loader import PROJECT_ROOT, ROOT, load_config
from .vision_client import VisionClient


OUTPUTS_ROOT = ROOT / "outputs" / "source_to_chat_turns01"
PREPARED_ROOT = OUTPUTS_ROOT / "_prepared_sources"
OUTPUT_ROOT = OUTPUTS_ROOT / "_case_runs"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest(source_output_dir: Path) -> dict[str, Any]:
    for name in ("block_manifest.json", "blocks_prepared.json", "turn_candidates_reviewed.json"):
        path = source_output_dir / name
        if path.exists():
            return read_json(path)
    raise FileNotFoundError(f"No block manifest found in {source_output_dir}")


def manifest_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("candidates"), list):
        return payload["candidates"]
    if isinstance(payload.get("blocks"), list):
        return payload["blocks"]
    return []


def resolve_source_output(source_output: str) -> Path:
    candidate = Path(source_output)
    if candidate.exists():
        return candidate
    prepared = PREPARED_ROOT / source_output
    if prepared.exists():
        return prepared
    return prepared


def load_case_images(source_output_dir: Path, limit: int | None = None) -> list[dict[str, Any]]:
    payload = load_manifest(source_output_dir)
    items = []
    for candidate in manifest_items(payload):
        prepared_path = ROOT / candidate.get("prepared_path", "")
        if not prepared_path.exists():
            continue
        items.append(
            {
                "block_id": candidate["block_id"],
                "order": candidate.get("order", 0),
                "prepared_path": str(prepared_path),
                "crop_box": candidate.get("crop_box", []),
                "source_ref": candidate.get("source_ref", ""),
            }
        )
    return items[:limit] if limit else items


def group_items(items: list[dict[str, Any]], mode: str, group_size: int) -> list[list[dict[str, Any]]]:
    if mode == "single":
        return [[item] for item in items]
    if mode == "whole":
        return [items]
    return [items[index : index + group_size] for index in range(0, len(items), group_size)]


def should_be_narration(text: str, triggers: list[str]) -> bool:
    return any(trigger and trigger in text for trigger in triggers)


def normalize_blocks(
    results: list[dict[str, Any]],
    image_items: list[dict[str, Any]],
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    image_map = {item["block_id"]: item for item in image_items}
    valid_speakers = set(rules.get("valid_speakers", ["male", "female", "narration", "system", "unknown"]))
    review_speakers = set(rules.get("review_speakers", ["unknown"]))
    narration_triggers = [str(item) for item in rules.get("narration_triggers", [])]
    blocks = []
    turn_index = 1
    for result in results:
        parsed = result.get("parsed", {})
        if isinstance(parsed.get("blocks"), list):
            for block in parsed["blocks"]:
                if not isinstance(block, dict):
                    continue
                block_id = str(block.get("block_id", ""))
                source = image_map.get(block_id, {})
                normalized_turns = []
                for turn in block.get("turns", []) if isinstance(block.get("turns", []), list) else []:
                    if not isinstance(turn, dict):
                        continue
                    text = str(turn.get("text", "")).strip()
                    speaker = str(turn.get("speaker", "unknown")).strip() or "unknown"
                    notes = str(turn.get("notes", "")).strip()
                    if speaker not in valid_speakers:
                        speaker = "unknown"
                    if should_be_narration(text, narration_triggers) and speaker in {"female", "unknown"}:
                        speaker = "narration"
                        notes = "; ".join(part for part in [notes, "postprocess: narration_trigger"] if part)
                    normalized_turns.append(
                        {
                            "turn_id": f"turn_{turn_index:04d}",
                            "speaker": speaker,
                            "text": text,
                            "time": turn.get("time", ""),
                            "confidence": turn.get("confidence", ""),
                            "reason": turn.get("reason", ""),
                            "source_block_id": block_id,
                            "source_image": source.get("prepared_path", ""),
                            "crop_box": source.get("crop_box", []),
                            "need_review": bool(turn.get("need_review", False)) or speaker in review_speakers,
                            "notes": notes,
                        }
                    )
                    turn_index += 1
                block["turns"] = normalized_turns
                if source:
                    block["source_image"] = source.get("prepared_path", "")
                    block["crop_box"] = source.get("crop_box", [])
                blocks.append(block)
    return blocks


def speaker_counts(blocks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        for turn in block.get("turns", []):
            speaker = str(turn.get("speaker", "unknown"))
            counts[speaker] = counts.get(speaker, 0) + 1
    return counts


def write_readable(path: Path, case_id: str, blocks: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        f"# {case_id} chat turns",
        "",
        f"- model: {summary.get('model')}",
        f"- mode: {summary.get('mode')}",
        f"- calls: {summary.get('call_count')}",
        f"- successes: {summary.get('success_count')}",
        f"- elapsed_seconds: {summary.get('elapsed_seconds')}",
        "",
    ]
    for block in blocks:
        lines.append(f"## {block.get('block_id', '')}")
        lines.append("")
        if block.get("extracted_text"):
            lines.append(str(block["extracted_text"]))
            lines.append("")
        for turn in block.get("turns", []):
            review = " | review" if turn.get("need_review") else ""
            lines.append(
                f"- {turn.get('speaker', 'unknown')} | {turn.get('confidence', '')}{review}: {turn.get('text', '')}"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def run(case_id: str, source_output: str, mode: str, limit: int | None) -> dict[str, Any]:
    config = load_config("vision_model_config.yaml")
    prompt = load_config("vision_prompt.yaml")
    rules = load_config("postprocess_rules.yaml")
    client = VisionClient(config, prompt)
    source_output_dir = resolve_source_output(source_output)
    items = load_case_images(source_output_dir, limit)
    groups = group_items(items, mode, int(config.get("max_images_per_call", 4)))
    output_dir = OUTPUT_ROOT / case_id / mode
    results = []
    start = time.time()
    for index, group in enumerate(groups, 1):
        call_start = time.time()
        response = client.extract_turns(case_id, group, mode)
        results.append(
            {
                "call_index": index,
                "block_ids": [item["block_id"] for item in group],
                "status": response["status"],
                "error": response.get("error", ""),
                "elapsed_seconds": round(time.time() - call_start, 2),
                "parsed": response.get("parsed", {}),
                "raw_text": response.get("raw_text", ""),
            }
        )
    blocks = normalize_blocks(results, items, rules)
    summary = {
        "case_id": case_id,
        "source_output": source_output,
        "mode": mode,
        "model": config.get("model"),
        "provider": config.get("provider"),
        "image_count": len(items),
        "call_count": len(results),
        "success_count": sum(1 for item in results if item["status"] == "model_success"),
        "failure_count": sum(1 for item in results if item["status"] != "model_success"),
        "elapsed_seconds": round(time.time() - start, 2),
        "status_counts": {},
        "speaker_counts": speaker_counts(blocks),
        "need_review_turns": sum(
            1 for block in blocks for turn in block.get("turns", []) if turn.get("need_review")
        ),
    }
    for item in results:
        summary["status_counts"][item["status"]] = summary["status_counts"].get(item["status"], 0) + 1
    write_json(output_dir / "raw_model_results.json", {"summary": summary, "results": results})
    write_json(output_dir / "chat_turns.json", {"summary": summary, "blocks": blocks})
    write_readable(output_dir / "chat_readable.md", case_id, blocks, summary)
    write_json(output_dir / "quality_report.json", summary)
    return {
        **summary,
        "output_dir": str(output_dir.relative_to(ROOT)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="source_to_chat_turns_pipeline01")
    parser.add_argument("--case-id", default="stt_006_bad_temper")
    parser.add_argument("--source-output", default="data1html_bad_temper")
    parser.add_argument("--mode", choices=["single", "group", "whole"], default="group")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(run(args.case_id, args.source_output, args.mode, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
