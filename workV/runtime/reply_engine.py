from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from workflow.common.io import resolve_path, write_json
from workV.common import OUTPUT_ROOT, load_config, load_prompt, timestamp_id
from workV.knowledge.search_segments import search_segments
from workV.model_client import ChatJsonClient
from workV.runtime.vision_understanding import dry_run_image_summary, understand_images


def run_reply(
    question: str,
    context: str = "",
    images: list[str] | None = None,
    index_path: str | None = None,
    batch_id: str = "reply_runs",
    dry_run: bool = False,
) -> dict[str, Any]:
    run_id = timestamp_id()
    output_dir = OUTPUT_ROOT / "runs" / batch_id / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    models = load_config("models.json")
    user_id = str(models.get("user_id", "71"))
    image_paths = [resolve_path(path) for path in (images or [])]
    image_data = image_payload(question, context, image_paths, models, user_id, dry_run)
    image_understanding = image_data.get("text", "")
    input_text = build_input_text(question, context, image_understanding)
    label_prompt = build_label_prompt(input_text)
    reply_client = ChatJsonClient("reply_model", models["reply_model"], user_id)

    if dry_run:
        labels = heuristic_labels(input_text)
        references = search_segments(input_text, labels, index_path)
        user_prompt = build_reply_prompt(input_text, labels, references)
        preview = {
            "status": "dry_run",
            "run_id": run_id,
            "input_text": input_text,
            "images": [str(path) for path in image_paths],
            "image_understanding": image_understanding,
            "vision_result": image_data.get("model_result", {}),
            "labels": labels,
            "reference_segments": references,
            "label_prompt": label_prompt,
            "reply_prompt": user_prompt,
            "output_dir": str(output_dir),
        }
        write_json(output_dir / "summary.json", preview)
        return preview

    label_result = reply_client.chat_json("只输出合法 JSON。", label_prompt)
    labels = extract_labels(label_result.get("parsed", {})) or heuristic_labels(input_text)
    references = search_segments(input_text, labels, index_path)
    reply_prompt = build_reply_prompt(input_text, labels, references)
    reply_result = reply_client.chat_json("只输出合法 JSON。", reply_prompt)
    parsed = reply_result.get("parsed", {}) if isinstance(reply_result.get("parsed"), dict) else {}
    result = normalize_reply_result(parsed, labels, references)
    summary = {
        "status": reply_result.get("status", ""),
        "run_id": run_id,
        "question": question,
        "context": context,
        "images": [str(path) for path in image_paths],
        "image_understanding": image_understanding,
        "vision_result": image_data.get("model_result", {}),
        "labels": labels,
        "reference_segments": references,
        "answer": result,
        "label_result": compact_model_result(label_result),
        "reply_result": compact_model_result(reply_result),
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def image_payload(
    question: str,
    context: str,
    image_paths: list[Path],
    models: dict[str, Any],
    user_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    if not image_paths:
        return {"text": "", "model_result": {}}
    if dry_run:
        return dry_run_image_summary(image_paths)
    return understand_images(question, context, image_paths, models, user_id)


def build_input_text(question: str, context: str, image_understanding: str = "") -> str:
    parts = ["用户问题：", question.strip()]
    if context.strip():
        parts.extend(["\n补充背景：", context.strip()])
    if image_understanding.strip():
        parts.extend(["\n截图/图片理解：", image_understanding.strip()])
    return "\n".join(parts)


def build_label_prompt(input_text: str) -> str:
    taxonomy = load_config("taxonomy_v01.json")
    principles = load_config("prompt_principles.json")
    return "\n\n".join(
        [
            load_prompt("reply_label_v01.md"),
            "标签枚举：",
            json.dumps(taxonomy.get("labels", {}), ensure_ascii=False, indent=2),
            "原则：",
            json.dumps(principles, ensure_ascii=False, indent=2),
            "当前输入：",
            input_text,
        ]
    )


def build_reply_prompt(input_text: str, labels: dict[str, Any], references: list[dict[str, Any]]) -> str:
    principles = load_config("prompt_principles.json")
    compact_refs = [compact_reference(item) for item in references]
    return "\n\n".join(
        [
            load_prompt("reply_generate_v01.md"),
            "原则：",
            json.dumps(principles, ensure_ascii=False, indent=2),
            "当前输入：",
            input_text,
            "当前基础标签：",
            json.dumps(labels, ensure_ascii=False, indent=2),
            "相似结构化案例片段：",
            json.dumps(compact_refs, ensure_ascii=False, indent=2),
        ]
    )


def extract_labels(parsed: dict[str, Any]) -> dict[str, Any]:
    labels = parsed.get("labels", parsed)
    if not isinstance(labels, dict):
        return {}
    return normalize_labels(labels)


def normalize_labels(labels: dict[str, Any]) -> dict[str, Any]:
    taxonomy = load_config("taxonomy_v01.json").get("labels", {})
    output = {}
    for field, allowed in taxonomy.items():
        value = labels.get(field, [] if field == "风险类型" else "")
        if field == "风险类型":
            if isinstance(value, str):
                value = [value] if value else []
            if not isinstance(value, list):
                value = []
            output[field] = [item for item in value if item in allowed]
        else:
            output[field] = value if value in allowed else (allowed[0] if allowed else "")
    return output


def heuristic_labels(text: str) -> dict[str, Any]:
    stage = "熟悉期"
    if any(word in text for word in ["刚加", "刚认识", "匹配", "第一次聊"]):
        stage = "刚认识"
    elif is_invite_context(text):
        stage = "邀约期"
    elif any(word in text for word in ["想你", "暧昧", "喜欢", "宝宝"]):
        stage = "暧昧升温期"

    female_state = "正常"
    if any(word in text for word in ["拒绝", "不想", "算了", "别", "不要"]):
        female_state = "拒绝"
    elif any(word in text for word in ["哈哈", "嗯", "哦", "好吧"]):
        female_state = "低投入"
    elif any(word in text for word in ["主动", "想见", "可以呀", "好啊"]):
        female_state = "热情"

    goal = "延续话题"
    strategy = "话题延展"
    risks: list[str] = []
    strength = "轻松"
    if stage == "邀约期":
        goal = "邀约"
        strategy = "模糊邀约"
    if female_state in {"冷淡", "防御", "拒绝"}:
        goal = "降压"
        strategy = "主动降压"
        strength = "安全"
    if text.count("?") + text.count("？") >= 2:
        risks.extend(["查户口", "连续追问"])
    if len(text) > 500:
        risks.append("长篇大论")
    return normalize_labels({"聊天阶段": stage, "女生状态": female_state, "男生目标": goal, "推荐策略": strategy, "风险类型": risks, "回复强度": strength})


def is_invite_context(text: str) -> bool:
    invite_words = ["约她", "约我", "约出来", "出来见", "见一面", "一起吃", "一起喝", "看电影", "喝咖啡", "周末有空", "哪天有空"]
    if any(word in text for word in invite_words):
        return True
    if "还没见面" in text or "没见面" in text or "未见面" in text:
        return False
    return "邀约" in text


def compact_reference(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": item.get("case_id", ""),
        "segment_id": item.get("segment_id", ""),
        "labels": item.get("labels", {}),
        "secondary_labels": item.get("secondary_labels", {}),
        "女生最后一句": item.get("女生最后一句", ""),
        "男生原回复": item.get("男生原回复", ""),
        "原回复评价": item.get("原回复评价", ""),
        "更优回复": item.get("更优回复", ""),
        "下一步建议": item.get("下一步建议", ""),
        "match_reasons": item.get("match_reasons", []),
        "score": item.get("score", 0),
    }


def normalize_reply_result(parsed: dict[str, Any], labels: dict[str, Any], references: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "reply": str(parsed.get("reply", "")),
        "coach_analysis": str(parsed.get("coach_analysis", "")),
        "labels": normalize_labels(parsed.get("labels", labels) if isinstance(parsed.get("labels", labels), dict) else labels),
        "risk_warning": str(parsed.get("risk_warning", "")),
        "next_step": str(parsed.get("next_step", "")),
        "reference_segments": parsed.get("reference_segments") if isinstance(parsed.get("reference_segments"), list) else [item.get("segment_id", "") for item in references],
        "debug": parsed.get("debug", {}) if isinstance(parsed.get("debug", {}), dict) else {},
    }


def compact_model_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status", ""),
        "model": result.get("model", ""),
        "client": result.get("client", ""),
        "error": result.get("error", ""),
        "elapsed_seconds": result.get("elapsed_seconds", 0),
        "usage": result.get("usage", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run workV reply flow.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--index-path")
    parser.add_argument("--batch-id", default="reply_runs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_reply(args.question, args.context, args.image, args.index_path, args.batch_id, args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
