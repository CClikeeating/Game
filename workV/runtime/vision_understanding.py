from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow.qingsheng_skill_runtime04.model_client import RuntimeModelClient
from workV.common import load_prompt


def understand_images(question: str, context: str, image_paths: list[Path], models: dict[str, Any], user_id: str) -> dict[str, Any]:
    vision_cfg = dict(models.get("vision_model", {}))
    vision_client = RuntimeModelClient("vision_model", vision_cfg, user_id)
    result = vision_client.chat(build_system_prompt(), build_user_prompt(question, context), image_paths)
    text = str(result.get("raw_text", "")).strip()
    if result.get("status") != "model_success":
        text = f"图片理解失败：{result.get('error', result.get('status', 'unknown'))}"
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


def build_system_prompt() -> str:
    return (
        "你是新版 MVP 的聊天截图理解助手，只输出可用于后续标签判断和回复建议的事实摘要。"
        "默认按聊天气泡位置判断说话人：左侧/白色气泡=女生或对方，右侧气泡=男生或用户；"
        "只有用户说明或截图内明确证据相反时才覆盖这个默认规则。"
    )


def build_user_prompt(question: str, context: str) -> str:
    base = load_prompt("image_understanding_v01.md")
    parts = [base, "用户问题：", question.strip()]
    if context.strip():
        parts.extend(["补充背景：", context.strip()])
    return "\n\n".join(parts)


def compact_vision_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status", ""),
        "model": result.get("model", ""),
        "client": result.get("client", ""),
        "error": result.get("error", ""),
        "elapsed_seconds": result.get("elapsed_seconds", 0),
        "usage": result.get("usage", {}),
    }
