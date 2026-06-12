from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path

from baiou.common.io import read_json as read_json_file
from baiou.common.io import write_json as write_json_file


IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: object) -> None:
    write_json_file(path, data)


def read_json(path: Path) -> object:
    return read_json_file(path)


def compact_text(text: str) -> str:
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"\b(\d)\s+(\d)(?=\s*(?:月|日|[：:]))", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_match(text: str) -> str:
    text = compact_text(text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)
    return text


def normalize_with_positions(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(text):
        if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", char):
            chars.append(char)
            positions.append(index)
    return "".join(chars), positions


def fuzzy_ratio(left: str, right: str) -> float:
    left_norm = normalize_for_match(left)
    right_norm = normalize_for_match(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def remove_overlap(previous: str, current: str, window: int = 320, threshold: float = 0.82) -> tuple[str, dict]:
    previous_tail = compact_text(previous)[-window:]
    current_clean = compact_text(current)
    current_head = current_clean[:window]
    best = {"removed_chars": 0, "ratio": 0.0, "method": "none"}
    if not previous_tail or not current_head:
        return current_clean, best

    prev_norm, _ = normalize_with_positions(previous_tail)
    curr_norm, curr_positions = normalize_with_positions(current_head)
    max_exact = min(len(prev_norm), len(curr_norm), 120)
    for offset in range(0, min(8, len(curr_norm)) + 1):
        for size in range(max_exact - offset, 5, -1):
            end = offset + size
            if end > len(curr_norm):
                continue
            if prev_norm[-size:] == curr_norm[offset:end]:
                original_end = curr_positions[end - 1] + 1
                return (
                    current_clean[original_end:].lstrip(),
                    {
                        "removed_chars": original_end,
                        "ratio": 1.0,
                        "method": "exact_normalized_prefix",
                        "offset": offset,
                        "matched_chars": size,
                    },
                )

    max_size = min(len(previous_tail), len(current_head), 180)
    for offset in range(0, min(24, len(current_head)) + 1):
        for size in range(max_size - offset, 7, -1):
            head_end = offset + size
            if head_end > len(current_head):
                continue
            tail = previous_tail[-size:]
            head = current_head[offset:head_end]
            ratio = fuzzy_ratio(tail, head)
            if ratio > best["ratio"]:
                best = {
                    "removed_chars": head_end,
                    "ratio": round(ratio, 3),
                    "method": "fuzzy_prefix",
                    "offset": offset,
                    "matched_chars": size,
                    "candidate_text": head,
                }
            if ratio >= max(threshold, 0.92):
                return current_clean[head_end:].lstrip(), best
    if best["ratio"] > 0:
        return current_clean, {
            "removed_chars": 0,
            "ratio": best["ratio"],
            "method": "candidate_only",
            "candidate_removed_chars": best.get("removed_chars", 0),
            "offset": best.get("offset", 0),
            "matched_chars": best.get("matched_chars", 0),
            "candidate_text": best.get("candidate_text", ""),
        }
    return current_clean, best


def normalize_turn_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def remove_adjacent_cross_block_duplicate_turns(blocks: list[dict]) -> int:
    previous_key = None
    previous_block_id = ""
    removed = 0
    for block in blocks:
        block_id = str(block.get("block_id", ""))
        kept = []
        for turn in block.get("turns", []):
            key = (turn.get("speaker"), normalize_turn_text(str(turn.get("text", ""))))
            if key[1] and key == previous_key and block_id != previous_block_id:
                removed += 1
                continue
            kept.append(turn)
            previous_key = key
            previous_block_id = block_id
        block["turns"] = kept
    return removed


def natural_key(path: Path) -> list[object]:
    parts: list[object] = []
    for piece in re.split(r"(\d+)", path.name.lower()):
        parts.append(int(piece) if piece.isdigit() else piece)
    return parts


def stable_source_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8", errors="ignore")).hexdigest()[:8]
    stem = re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_").lower()
    if not stem:
        stem = "source"
    return f"{stem[:36]}_{digest}"


