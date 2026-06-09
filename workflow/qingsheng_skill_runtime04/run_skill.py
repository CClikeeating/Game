from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .model_client import RuntimeModelClient


ROOT = Path.cwd()
CONFIG_ROOT = ROOT / "workflow" / "qingsheng_skill_runtime04" / "config"


def run_skill(
    question: str,
    context: str = "",
    images: list[str] | None = None,
    batch_id: str | None = None,
    experience_pack: str | None = None,
    mode: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    runtime = read_json(CONFIG_ROOT / "runtime.json")
    models = read_json(CONFIG_ROOT / "models.json")
    batch_id = batch_id or runtime["output"]["default_batch_id"]
    image_paths = [resolve_path(path) for path in (images or [])]
    validate_images(image_paths)
    runtime_mode = normalize_mode(mode or runtime.get("mode", {}).get("default", "rag"))

    skill_prompt = build_system_prompt(runtime)
    selected_cases = retrieve_cases(question, context, runtime, experience_pack)
    image_understanding = ""
    user_prompt = build_user_prompt(question, context, selected_cases, image_paths, runtime)

    output_root = resolve_path(runtime["output"]["root"]) / batch_id
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prompt_path = output_root / f"{run_id}_prompt_preview.json"
    result_path = output_root / f"{run_id}_result.json"

    if dry_run:
        write_prompt_preview(prompt_path, question, context, image_paths, selected_cases, skill_prompt, user_prompt, image_understanding, runtime_mode)
        result = {
            "status": "dry_run",
            "answer": "",
            "model_result": {},
            "vision_result": {},
            "mode": runtime_mode,
            "prompt_preview": str(prompt_path),
            "result_path": str(result_path),
        }
        write_json(result_path, result)
        return result

    vision_result: dict[str, Any] = {}
    if image_paths and runtime_mode == "fast":
        vision_client = RuntimeModelClient("vision_model", models["vision_model"], str(models.get("user_id", "0")))
        model_result = vision_client.chat(skill_prompt, user_prompt, image_paths)
        result = {
            "status": model_result["status"],
            "answer": model_result.get("raw_text", ""),
            "model_result": model_result,
            "vision_result": model_result,
            "mode": runtime_mode,
            "prompt_preview": str(prompt_path),
            "result_path": str(result_path),
        }
        write_prompt_preview(prompt_path, question, context, image_paths, selected_cases, skill_prompt, user_prompt, image_understanding, runtime_mode)
        write_json(result_path, result)
        return result

    if image_paths:
        vision_client = RuntimeModelClient("vision_model", models["vision_model"], str(models.get("user_id", "0")))
        vision_prompt = build_image_understanding_prompt(question, context)
        vision_result = vision_client.chat(build_image_understanding_system_prompt(), vision_prompt, image_paths)
        if vision_result.get("status") == "model_success":
            image_understanding = str(vision_result.get("raw_text", "")).strip()
        else:
            image_understanding = f"图片理解失败：{vision_result.get('error', vision_result.get('status', 'unknown'))}"
        user_prompt = build_user_prompt(
            question,
            context,
            selected_cases,
            [],
            runtime,
            image_understanding=image_understanding,
        )

    write_prompt_preview(prompt_path, question, context, image_paths, selected_cases, skill_prompt, user_prompt, image_understanding, runtime_mode)
    client = RuntimeModelClient("text_model", models["text_model"], str(models.get("user_id", "0")))
    model_result = client.chat(skill_prompt, user_prompt, [])
    result = {
        "status": model_result["status"],
        "answer": model_result.get("raw_text", ""),
        "model_result": model_result,
        "vision_result": vision_result,
        "mode": runtime_mode,
        "prompt_preview": str(prompt_path),
        "result_path": str(result_path),
    }
    write_json(result_path, result)
    return result


def write_prompt_preview(
    prompt_path: Path,
    question: str,
    context: str,
    image_paths: list[Path],
    selected_cases: list[dict[str, Any]],
    skill_prompt: str,
    user_prompt: str,
    image_understanding: str,
    mode: str,
) -> None:
    write_json(
        prompt_path,
        {
            "question": question,
            "context": context,
            "images": [str(path) for path in image_paths],
            "mode": mode,
            "image_understanding": image_understanding,
            "selected_cases": selected_cases,
            "system_prompt_chars": len(skill_prompt),
            "user_prompt": user_prompt,
        },
    )


def normalize_mode(value: str) -> str:
    mode = str(value or "rag").strip().lower()
    if mode == "auto":
        return "rag"
    if mode in {"fast", "rag"}:
        return mode
    return "rag"


def build_system_prompt(runtime: dict[str, Any]) -> str:
    skill = runtime["skill"]
    prompt_cfg = runtime["prompt"]
    skill_md = trim(read_text(resolve_path(skill["skill_md"])), int(prompt_cfg["max_skill_chars"]))
    references = []
    ref_root = resolve_path(skill["references_dir"])
    for name in skill.get("default_reference_files", []):
        path = ref_root / name
        if path.exists():
            references.append(f"\n\n# reference: {name}\n{read_text(path)}")
    references_text = trim("\n".join(references), int(prompt_cfg["max_reference_chars"]))
    return "\n\n".join(
        [
            prompt_cfg.get("product_mode_note", ""),
            format_style_rules(prompt_cfg.get("answer_style_rules", [])),
            "下面是 qingsheng skill 主手册，请严格按它的风格、流程和边界回答。",
            skill_md,
            "下面是本次运行预加载的参考资料。仍然按需使用，不要在回答里暴露文件名。",
            references_text,
        ]
    ).strip()


def build_user_prompt(
    question: str,
    context: str,
    selected_cases: list[dict[str, Any]],
    image_paths: list[Path],
    runtime: dict[str, Any],
    image_understanding: str = "",
) -> str:
    parts = [
        "用户问题：",
        question.strip(),
    ]
    if context.strip():
        parts.extend(["\n用户额外补充背景/手动提示：", context.strip()])
    if image_paths:
        parts.append(
            "\n用户同时上传了图片。请直接读取图片内容，结合文字背景判断；如果图片里是聊天截图，请把它当作核心上下文。聊天截图默认规则：右侧绿色气泡=男方/用户，左侧白色气泡=女方/对方，除非图片里有明确相反证据。"
        )
    if image_understanding.strip():
        parts.extend(
            [
                "\n图片理解内容（由视觉模型从用户图片中提取）：",
                image_understanding.strip(),
                "\n请用以上图片理解内容作为知识库检索查询的一部分，并结合检索到的案例回答用户。",
            ]
        )
    if selected_cases:
        parts.append("\n可参考的经验案例（只作为参考，不要机械套用）：")
        for case in selected_cases:
            parts.append(format_case(case, int(runtime["experience"]["max_case_chars"])))
    parts.append(
        "\n回答要求：先解决用户当下问题。需要话术时给可直接复制发送的中文。默认短、准、像真人，不要写成分析报告；如果是 /自动，第一行必须是 [发送]。"
    )
    return "\n".join(parts)


def build_image_understanding_system_prompt() -> str:
    return (
        "你是聊天截图理解助手，只负责把用户上传的图片转成可用于知识库检索的中文文本摘要。"
        "不要给最终回复建议，不要长篇分析。"
        "识别微信聊天截图时默认：右侧绿色气泡=男方/用户，左侧白色气泡=女方/对方，系统提示单独标记；除非图片里有明确相反证据。"
    )


def build_image_understanding_prompt(question: str, context: str) -> str:
    parts = [
        "请读取用户上传的图片。如果是聊天截图，请提取：",
        "1. 可见聊天内容，按男/女/系统/旁白区分；",
        "2. 当前最关键的几句原话；",
        "3. 女方可能释放的信号，只做候选描述，不做最终判断；",
        "4. 用户真正想问的问题；",
        "5. 适合用于案例知识库检索的关键词。",
        "",
        "微信气泡默认规则：右侧绿色气泡=男方/用户；左侧白色气泡=女方/对方；系统时间/提示=系统；表情包按发送方归属标注。",
        "输出要简洁，保留原句，不要编造图片外内容。",
        f"用户问题：{question.strip()}",
    ]
    if context.strip():
        parts.append(f"用户补充背景：{context.strip()}")
    return "\n".join(parts)


def format_style_rules(rules: list[str]) -> str:
    if not rules:
        return ""
    lines = ["本 runtime 的产品化输出约束，高于长篇分析倾向："]
    lines.extend(f"- {rule}" for rule in rules)
    return "\n".join(lines)


def retrieve_cases(
    question: str,
    context: str,
    runtime: dict[str, Any],
    experience_pack: str | None,
) -> list[dict[str, Any]]:
    exp_cfg = runtime["experience"]
    if not exp_cfg.get("enabled", True):
        return []
    pack_path = resolve_path(experience_pack or exp_cfg["default_pack"])
    if not pack_path.exists():
        return []
    data = read_json(pack_path)
    cases = data.get("cases", []) if isinstance(data, dict) else []
    query = f"{question}\n{context}"
    scored = [(case_score(query, case), case) for case in cases]
    scored = [(score, case) for score, case in scored if score > 0]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [case for _, case in scored[: int(exp_cfg.get("top_k", 3))]]


def case_score(query: str, case: dict[str, Any]) -> int:
    haystack = json.dumps(case, ensure_ascii=False)
    tokens = extract_tokens(query)
    return sum(haystack.count(token) for token in tokens)


def extract_tokens(text: str) -> list[str]:
    raw = [item.strip(" ，。！？,.!?;；:：\n\t") for item in text.split()]
    tokens = [item for item in raw if len(item) >= 2]
    fixed = ["邀约", "见面", "表情", "自拍", "冷场", "不回", "约会", "亲密", "老公", "男朋友", "女朋友", "怎么回", "微信"]
    tokens.extend(token for token in fixed if token in text)
    return list(dict.fromkeys(tokens))


def format_case(case: dict[str, Any], max_chars: int) -> str:
    text = json.dumps(
        {
            "case_id": case.get("case_id", ""),
            "stage": case.get("stage_label", ""),
            "outcome": case.get("outcome", ""),
            "signals": case.get("signals", []),
            "good_replies": case.get("good_replies", []),
            "observed_good_reply": case.get("observed_good_reply", {}),
            "next_reply": case.get("next_reply", ""),
            "rules": case.get("transferable_rules", []),
        },
        ensure_ascii=False,
    )
    return trim(text, max_chars)


def validate_images(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise ValueError(f"unsupported image type: {path}")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def trim(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + "\n...[truncated]"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run qingsheng skill with text, optional images, and experience pack.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--batch-id")
    parser.add_argument("--experience-pack")
    parser.add_argument("--mode", choices=["fast", "rag", "auto"], help="图片输入模式：fast 直接视觉回答；rag/auto 先视觉摘要再检索知识库。")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_skill(
        question=args.question,
        context=args.context,
        images=args.image,
        batch_id=args.batch_id,
        experience_pack=args.experience_pack,
        mode=args.mode,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
