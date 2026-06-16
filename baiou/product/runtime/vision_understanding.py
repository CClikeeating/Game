from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from baiou.common.runtime_model_client import RuntimeModelClient
from baiou.product.common import load_prompt


VISION_STYLE_FULL = "full"
VISION_STYLE_DIALOGUE = "dialogue"


def understand_images(
    question: str,
    context: str,
    image_paths: list[Path],
    models: dict[str, Any],
    user_id: str,
    style: str = VISION_STYLE_FULL,
) -> dict[str, Any]:
    vision_cfg = dict(models.get("vision_model", {}))
    style = normalize_vision_style(style)
    if style == VISION_STYLE_DIALOGUE:
        vision_cfg["max_tokens"] = min(int(vision_cfg.get("max_tokens", 5000)), int(vision_cfg.get("dialogue_max_tokens", 1600)))
    vision_client = RuntimeModelClient("vision_model", vision_cfg, user_id)
    result = vision_client.chat(build_system_prompt(style), build_user_prompt(question, context, style), image_paths)
    text = str(result.get("raw_text", "")).strip()
    if result.get("status") != "model_success":
        text = f"图片理解失败：{result.get('error', result.get('status', 'unknown'))}"
    else:
        text = correct_vision_attribution(text)
    return {"text": text, "model_result": compact_vision_result(result)}


def dry_run_image_summary(image_paths: list[Path]) -> dict[str, Any]:
    names = [path.name for path in image_paths]
    return {
        "text": f"dry_run：已收到 {len(image_paths)} 张图片，未调用视觉模型。图片文件：" + "、".join(names),
        "model_result": {
            "status": "skipped_dry_run",
            "model": "vision_model",
            "client": "vision_model",
            "error": "",
            "elapsed_seconds": 0,
            "usage": {},
        },
    }


def build_system_prompt(style: str = VISION_STYLE_FULL) -> str:
    if normalize_vision_style(style) == VISION_STYLE_DIALOGUE:
        return (
            "你是新版 MVP 的聊天截图转写助手。只提取截图里可见的聊天话轮和回复定位，不做情感分析。"
            "默认按聊天气泡位置判断说话人：左侧/白色气泡=女生或对方，右侧/绿色气泡=男生或用户；"
            "只有用户补充背景、截图内头像/昵称/系统提示等明确证据相反时，才覆盖默认规则。"
            "输出要短，优先保留原句，方便后续模型直接判断怎么回复。"
        )
    return (
        "你是新版 MVP 的聊天截图理解助手，只输出可用于后续标签判断和回复建议的事实摘要。"
        "这是产品端图片理解规则：默认按聊天气泡位置判断说话人，左侧/白色气泡=女生或对方，"
        "右侧/绿色气泡=男生或用户；只有用户补充背景、截图内头像/昵称/系统提示等明确证据相反时，"
        "才覆盖默认规则。必须先按可见顺序列出结构化话轮表，再从话轮中提取女生/对方最后一句、"
        "男生/用户最近回复、用户真正要回复的位置和当前可见局势，并做归属一致性自检。"
    )


def build_user_prompt(question: str, context: str, style: str = VISION_STYLE_FULL) -> str:
    prompt_name = "image_understanding_dialogue_v01.md" if normalize_vision_style(style) == VISION_STYLE_DIALOGUE else "image_understanding_v01.md"
    base = load_prompt(prompt_name)
    parts = [base, "用户问题：", question.strip()]
    if context.strip():
        parts.extend(["补充背景：", context.strip()])
    return "\n\n".join(parts)


def normalize_vision_style(style: str) -> str:
    return VISION_STYLE_DIALOGUE if str(style).strip().lower() in {"dialogue", "fast", "short"} else VISION_STYLE_FULL


def correct_vision_attribution(text: str) -> str:
    turns = parse_structured_turns(text)
    if not turns:
        return text
    female_last = last_text_turn(turns, "女生/对方")
    male_last = last_text_turn(turns, "男生/用户")
    if not female_last and not male_last:
        return text

    lines = [
        "",
        "程序校正（优先使用）：",
        "- 校正依据：从“结构化可见话轮”按可见顺序和归属字段抽取，避免后续自然语言摘要跨归属拿句子。",
    ]
    if female_last:
        lines.append(f"- 女生/对方最后一句：{female_last}")
    if male_last:
        lines.append(f"- 男生/用户最近回复：{male_last}")
    if female_last:
        lines.append(f"- 用户真正要回复的位置：女生/对方最后一句：{female_last}")
    lines.append("- 一致性规则：左侧/白色气泡只可作为女生/对方内容；右侧/绿色气泡只可作为男生/用户内容，除非有明确覆盖证据。")
    return text.rstrip() + "\n" + "\n".join(lines)


def parse_structured_turns(text: str) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4 or "位置" in cells[0] or "归属" in cells[1]:
            continue
        position, speaker, content_type, content = cells[:4]
        speaker = normalize_speaker(speaker)
        if speaker:
            turns.append(
                {
                    "position": position,
                    "speaker": speaker,
                    "content_type": content_type,
                    "content": clean_turn_content(content),
                }
            )
    return turns


def normalize_speaker(value: str) -> str:
    text = re.sub(r"[*`\s]+", "", value)
    if "女生" in text or "对方" in text or text == "female":
        return "女生/对方"
    if "男生" in text or "用户" in text or text == "male":
        return "男生/用户"
    return ""


def clean_turn_content(value: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", value).strip()
    text = re.sub(r"^[“\"']|[”\"']$", "", text).strip()
    return text


def last_text_turn(turns: list[dict[str, str]], speaker: str) -> str:
    for turn in reversed(turns):
        if turn.get("speaker") == speaker and "文字" in turn.get("content_type", "") and turn.get("content"):
            return turn["content"]
    return ""


def compact_vision_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status", ""),
        "model": result.get("model", ""),
        "client": result.get("client", ""),
        "error": result.get("error", ""),
        "elapsed_seconds": result.get("elapsed_seconds", 0),
        "usage": result.get("usage", {}),
    }
