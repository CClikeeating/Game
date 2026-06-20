from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from baiou.common.io import resolve_path, write_json
from baiou.common.runtime_model_client import RuntimeModelClient
from baiou.case_pipeline.knowledge.search_segments import search_segments
from baiou.common.chat_json_client import ChatJsonClient, parse_json_content
from baiou.product.runtime.vision_understanding import VISION_STYLE_DIALOGUE, VISION_STYLE_FULL, dry_run_image_summary, understand_images
from baiou.product.common import OUTPUT_ROOT, load_config, load_prompt, timestamp_id

MODE_QUALITY_LOCAL = "quality_local"
MODE_BAILIAN_RAG_FAST = "bailian_rag_fast"
MODE_BAILIAN_RAG_QUALITY = "bailian_rag_quality"
MODE_BAILIAN_RAG_STRATEGY_FAST = "bailian_rag_strategy_fast"
MODE_BAILIAN_RAG_STRATEGY_QUALITY = "bailian_rag_strategy_quality"

STRATEGY_CHOICES = [
    "轻承接",
    "轻推进",
    "轻撤退",
    "暧昧试探",
    "暧昧推进",
    "关系框架升级",
    "高张力推进",
    "转移话题",
    "风险提醒",
]

SCENE_TYPE_CHOICES = [
    "提问破解",
    "筛选标准",
    "推开否定",
    "主动邀约拉扯",
    "关系节奏测试",
    "关系框架升级",
    "极短追问",
    "事实纠偏",
    "现实状态边界",
    "暧昧进攻",
    "其他",
]

DEFAULT_LABEL_ALIASES = {
    "聊天阶段": {
        "初识": "刚认识",
        "破冰": "破冰期",
        "邀约期": "高意向推进期",
        "暧昧升温": "暧昧升温期",
        "暧昧": "暧昧升温期",
    },
    "关系推进目标": {
        "亲密升级": "亲密升级推进",
        "性关系": "性关系推进",
    },
    "男生目标": {
        "维持框架": "升温",
        "推拉": "升温",
        "推进关系": "升温",
        "聊天": "延续话题",
    },
    "推荐策略": {
        "挑战": "轻微调侃",
        "推拉": "轻微调侃",
        "调侃": "轻微调侃",
        "升温": "情绪升温",
        "性张力": "性张力玩笑",
    },
    "回复强度": {
        "低": "安全",
        "弱": "安全",
        "中": "调侃",
        "中等": "调侃",
        "高": "推进",
        "强": "推进",
    },
    "高热度信号": {
        "亲密升级": "亲密升级信号",
        "性张力": "性张力玩笑",
    },
}

IMAGE_INPUT_HINT = (
    "回复定位要求：优先使用截图/图片理解里的说话人归属依据、女生/对方最后一句、男生/用户最近回复、"
    "用户真正要回复的位置和当前可见局势；若存在“程序校正（优先使用）”，以程序校正为准；"
    "默认左侧/白色气泡=女生或对方，右侧/绿色气泡=男生或用户。"
)

RELATIONSHIP_PACE_CUES = [
    "发展太快",
    "太快了",
    "是不是太快",
    "会不会太快",
    "进展太快",
    "节奏太快",
    "才认识几天",
    "刚认识几天",
    "认识几天就在一起",
]

CLEAR_BOUNDARY_CUES = [
    "我不想这样",
    "不想这样",
    "别这样",
    "不要这样",
    "我不舒服",
    "不舒服",
    "先别推进",
    "先别说",
    "不要再说",
    "别说了",
    "不想聊这个",
    "别聊这个",
    "不想继续",
    "到此为止",
]

RELATIONSHIP_PACE_RULE = (
    "关系节奏质疑不能进入顺从模式：女生说“发展太快”“是不是太快了”“才认识几天就在一起了”等，"
    "如果没有明确停止、拒绝或不舒服证据，不要默认回复“好，听你的”“按你的节奏来”“那我们慢一点”；"
    "也不要用“快慢不重要”“快慢是相对的”这类否定式开头。优先学习可迁移的“反抛定义权”动作：不接受对方预设结论，"
    "把对方的表层判断拆成“表面维度”和“背后担忧”，用一个短问题把定义权拿回来，再用更高层标准重定义局势。"
    "更高层标准要贴合上下文，可从认真程度、舒服程度、确定感、相处质量、边界感、投入一致性中选择，不要固定套某一句。"
    "没有明确边界时，labels 不要标成女生状态=防御/拒绝、男生目标=降压、"
    "推荐策略=主动降压。明确边界时只收住当前推进并转移话题，不道歉自证、不交出整体框架。"
)

RELATIONSHIP_PACE_MODE_HINTS = {
    "fast": "快速模式表达差异：关系节奏质疑优先给一句短反抛，只拿回定义权，不展开解释。",
    "quality": "质量模式表达差异：关系节奏质疑优先用“短反抛 + 轻重定义”，允许比快速模式多半句标准重定义。",
    "strategy_fast": "策略实验模式表达差异：关系节奏质疑可以更松弛一点，用反抛问题把表层质疑转成背后担忧。",
    "strategy_quality": "策略质量模式表达差异：关系节奏质疑用稳一点的反抛定义权，并明确更高层评价标准。",
}

TEXT_STRUCTURED_INPUT_RULE = (
    "文本结构输入规则：如果当前输入已经包含 turn_ 对话行、女生/对方最后一句、文本评测入口或文本极速入口，"
    "就把这些文字当作完整当前聊天依据；禁止要求用户再上传截图、图片或聊天记录，也不要说缺少上下文。"
)

FRAME_ACTION_RULE = (
    "话语动作优先于字面接话：先判断女生这句话是在索取理由、筛选标准、推开否定、主动邀约、索要补偿、极短追问、"
    "玩笑命令、示弱分享还是普通承接，再选动作。索取理由时不要自证，转成关系张力或选择困境；筛选标准时回答事实并保留自有标准，"
    "不要表现成只为她改变；推开否定时不要顺势后撤，优先拿回定义权或轻推回去；主动邀约或命令不必总是立即接受，可用轻推开、"
    "反客为主或设置自己的标准保持框架；极短追问优先极短直给，不为了显聪明而加包装；玩笑对象明确时优先围绕对象做轻损调侃，"
    "不要变成后勤安排；示弱或状态分享先接住状态，避免查户口和说教。"
)

FRAME_ACTION_DETAIL_RULE = (
    "动作子规则要可迁移而不是套例句：极短追问如果只是补全上一句的对象、归属或态度，先直给核心信息，"
    "不要用反问、你猜、吃醋了等包装盖过答案；如果缺少可恢复上下文，短人称追问优先回到当前暧昧对象或接收者，"
    "不要凭空引入第三方。女生主动邀约、命令或高主动推进时，不要只接安排，先保留选择权，"
    "可标记她的主动、反客为主、设一点自己的标准，再给方向；如果她抛出低价值或太顺手的玩法，可以拒绝原方案并换成更有吸引力的具体方案。"
    "女生把你定义成太急、太渣、太主动或太容易时，不要解释自证，也不要只反问，要给出自己的选择标准，"
    "把判断标准转回选择感、感觉、投入一致性和自有边界；女生用“撩不到/没机会/不可能”等否定你时，不要自我撤退，"
    "优先否定她的预设或把筛选权拿回来。女生误读你评价的对象时，事实纠偏优先级高于夸奖和哄，先纠正指代再轻调侃。"
    "女生处在上课、忙、身体不适等现实状态时，先收住当前干扰，再留一个低压力的具体后续钩子；"
    "女生表达愿意等你、分享快乐或照顾互动节奏时，先接住这份投入，再把话题引到她当下可分享的具体内容，"
    "不要反过来筛选她够不够甜、够不够有趣。已有玩笑空间或暧昧承接时可以更大胆一点，但必须短、自然、有兜底。"
)

HIGH_FRAME_SCOPE_RULE = (
    "高框架推拉模式只服务高张力场景：破解测试、筛选/否定、推开、主动邀约拉扯、暧昧进攻、关系节奏重定义。"
    "不要承担普通日常接话、寒暄、查户口、长篇安慰或泛泛建议。输出永远是一句微信可发短回复。"
)

HIGH_FRAME_CORE_RULE = (
    "核心动作：1) 不进对方预设，不解释自证，不自我撤退；2) 先识别话语动作，再选择反抛定义权、拿回筛选权、"
    "反客为主、轻推回去、事实纠偏、极短直给、现实状态收住后留钩子；3) 主动邀约/命令不能直接答应，先保留选择权；"
    "4) 关系节奏质疑没有明确停止/不舒服证据时，按推开式测试处理，不能进入顺从模式，不回“好，听你的/按你的节奏来/那我们慢一点”，"
    "不用“快慢不重要”否定感受，要拆表面维度和背后担忧，用更高层标准重定义，且不要固定输出同一句；labels 不要写男生目标=降压；"
    "5) 明确边界只收住当前推进并换话题，不道歉自证、不交出整体框架；6) 有玩笑空间可暧昧进攻，但短、自然、有兜底；"
    "7) 补偿、奖励、撒娇索取类场景要给一点甜头或暧昧想象，再保留框架，不能只冷冷地设门槛；"
    "8) 具体物件/食物/表情/地点/药品出现时，优先贴对象特征轻损或暧昧联想，不要泛泛做资格筛选；"
    "9) 当女生把推进权抛回来时，不要把回复写成“女生需要证明自己”，也不要把轻门槛落成“看你表现”一类单向筛选。"
    "优先把她的问题转成更高层的暧昧框架：临时还是长期、表面便宜还是真正喜欢、占有感还是双向选择。"
    "可以轻筛选，但要先给情绪价值和关系想象，不要变成审查、要挟或价值资格评判。"
)

HIGH_FRAME_FORBID_RULE = (
    "禁止：跪舔、讨好、长篇解释、PUA、油腻强压、连续追问、默认接受安排、你猜/吃醋了替代直给、"
    "顺着误会哄、缺证据编造经历地点、把真实边界当测试。"
)

DAILY_FAST_SCOPE_RULE = (
    "日常快速回复模式只服务安全无压力的低压力聊天：接话、顺着当前话题聊下去、轻松转移、状态承接、普通关心、轻微暧昧。"
    "它不承担破解测试、进攻推进、高框架反制、强邀约或复杂关系分析；这些留给策略质量模式。"
)

DAILY_FAST_CORE_RULE = (
    "核心动作：1) 先接住对方这句话的情绪或信息，再给一个容易回复的下一句；2) 回复短、自然、无压力，像微信里随手能发；"
    "3) 可以带一点轻微暧昧或俏皮，但不要强撩、压迫、反击、说教；4) 对方忙、累、身体不舒服或明确不想聊时，先收住当前推进，"
    "轻轻换话题或留一个低压力钩子；5) 关系节奏这类含混担忧不要顺从投降，也不要高强度破解，只轻承接担忧并把话题带回舒服相处。"
)

DAILY_FAST_FORBID_RULE = (
    "禁止：长篇解释、连续追问、查户口、PUA、油腻强压、默认道歉自证、跪舔讨好、把普通聊天硬判成废物测试、"
    "主动加入高框架/推拉/进攻/反制等策略词。"
)


def run_reply(
    question: str,
    context: str = "",
    images: list[str] | None = None,
    index_path: str | None = None,
    batch_id: str = "reply_runs",
    dry_run: bool = False,
    mode: str | None = None,
) -> dict[str, Any]:
    run_id = timestamp_id()
    output_dir = OUTPUT_ROOT / "runs" / batch_id / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    models = load_config("models.json")
    runtime_mode = normalize_mode(mode)
    user_id = resolve_user_id(models, runtime_mode)
    image_paths = [resolve_path(path) for path in (images or [])]
    image_data = image_payload(question, context, image_paths, models, user_id, dry_run, vision_style_for_mode(models, runtime_mode))
    image_understanding = image_data.get("text", "")
    input_text = build_input_text(question, context, image_understanding)
    if runtime_mode in {MODE_BAILIAN_RAG_FAST, MODE_BAILIAN_RAG_QUALITY, MODE_BAILIAN_RAG_STRATEGY_FAST, MODE_BAILIAN_RAG_STRATEGY_QUALITY}:
        return run_bailian_rag_fast(
            run_id,
            output_dir,
            question,
            context,
            image_paths,
            image_data,
            image_understanding,
            input_text,
            models,
            user_id,
            dry_run,
            quality_mode=runtime_mode == MODE_BAILIAN_RAG_QUALITY,
            strategy_mode=runtime_mode == MODE_BAILIAN_RAG_STRATEGY_FAST,
            strategy_quality_mode=runtime_mode == MODE_BAILIAN_RAG_STRATEGY_QUALITY,
        )

    label_prompt = build_label_prompt(input_text)
    reply_client = ChatJsonClient("reply_model", models["reply_model"], user_id)

    if dry_run:
        labels = heuristic_labels(input_text)
        references = search_segments(input_text, labels, index_path)
        user_prompt = build_reply_prompt(input_text, labels, references)
        preview = {
            "status": "dry_run",
            "mode": runtime_mode,
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
    result = normalize_reply_result(parsed, labels, references, input_text)
    summary = {
        "status": reply_result.get("status", ""),
        "mode": runtime_mode,
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


def run_bailian_rag_fast(
    run_id: str,
    output_dir: Path,
    question: str,
    context: str,
    image_paths: list[Path],
    image_data: dict[str, Any],
    image_understanding: str,
    input_text: str,
    models: dict[str, Any],
    user_id: str,
    dry_run: bool,
    quality_mode: bool = False,
    strategy_mode: bool = False,
    strategy_quality_mode: bool = False,
) -> dict[str, Any]:
    mode_name = (
        MODE_BAILIAN_RAG_STRATEGY_QUALITY
        if strategy_quality_mode
        else MODE_BAILIAN_RAG_STRATEGY_FAST
        if strategy_mode
        else MODE_BAILIAN_RAG_QUALITY
        if quality_mode
        else MODE_BAILIAN_RAG_FAST
    )
    label_result: dict[str, Any] = {}
    quality_guidance: dict[str, Any] = {}
    strategy_guidance: dict[str, Any] = {}
    labels: dict[str, Any] = {}
    if quality_mode:
        if dry_run:
            labels = heuristic_labels(input_text)
            quality_guidance = heuristic_quality_guidance(input_text, labels)
        else:
            label_client = ChatJsonClient("reply_quality_label_model", quality_label_config(models), user_id)
            label_result = label_client.chat_json("只输出合法 JSON。", build_quality_label_prompt(input_text))
            quality_guidance = normalize_quality_guidance(label_result.get("parsed", {}))
            labels = quality_guidance.get("labels", {}) if isinstance(quality_guidance.get("labels", {}), dict) else {}
            labels = normalize_labels(labels) if labels else heuristic_labels(input_text)
            quality_guidance["labels"] = labels
    if strategy_quality_mode:
        if dry_run:
            labels = heuristic_labels(input_text)
            strategy_guidance = heuristic_strategy_guidance(input_text, labels)
        else:
            label_client = ChatJsonClient("reply_strategy_model", strategy_label_config(models), user_id)
            label_result = label_client.chat_json("只输出合法 JSON。", build_strategy_label_prompt(input_text))
            strategy_guidance = normalize_strategy_guidance(label_result.get("parsed", {}), input_text)
            labels = strategy_guidance.get("labels", {}) if isinstance(strategy_guidance.get("labels", {}), dict) else {}
            labels = normalize_labels(labels) if labels else heuristic_labels(input_text)
            strategy_guidance["labels"] = labels
    reply_prompt = build_bailian_rag_prompt(
        input_text,
        quality_guidance if quality_mode else None,
        strategy_mode=strategy_mode,
        strategy_guidance=strategy_guidance if strategy_quality_mode else None,
    )
    if dry_run:
        preview = {
            "status": "dry_run",
            "mode": mode_name,
            "run_id": run_id,
            "input_text": input_text,
            "images": [str(path) for path in image_paths],
            "image_understanding": image_understanding,
            "vision_result": image_data.get("model_result", {}),
            "labels": labels,
            "quality_guidance": quality_guidance,
            "strategy_guidance": strategy_guidance if strategy_quality_mode else strategy_fast_guidance() if strategy_mode else {},
            "reference_segments": [],
            "label_result": label_result,
            "reply_prompt": reply_prompt,
            "output_dir": str(output_dir),
        }
        write_json(output_dir / "summary.json", preview)
        return preview

    rag_cfg, error = bailian_rag_config(models)
    if error:
        summary = unavailable_bailian_summary(run_id, output_dir, question, context, image_paths, image_data, image_understanding, error, mode_name)
        if quality_guidance:
            summary["quality_guidance"] = quality_guidance
        if label_result:
            summary["label_result"] = compact_model_result(label_result)
        write_json(output_dir / "summary.json", summary)
        return summary

    reply_result = RuntimeModelClient("reply_rag_model", rag_cfg, user_id).chat("只输出合法 JSON。", reply_prompt, [])
    parsed = parse_json_content(reply_result.get("raw_text", ""))
    if reply_result.get("status") == "model_success" and not isinstance(parsed, dict):
        reply_result = dict(reply_result)
        reply_result["status"] = "model_json_invalid"
    parsed = parsed if isinstance(parsed, dict) else {}
    references = compact_rag_references(reply_result.get("references", []))
    labels = extract_labels(parsed)
    answer = normalize_reply_result(parsed, labels, references, input_text)
    summary = {
        "status": reply_result.get("status", ""),
        "mode": mode_name,
        "run_id": run_id,
        "question": question,
        "context": context,
        "images": [str(path) for path in image_paths],
        "image_understanding": image_understanding,
        "vision_result": image_data.get("model_result", {}),
        "labels": answer.get("labels", {}),
        "quality_guidance": quality_guidance,
        "strategy_guidance": strategy_guidance if strategy_quality_mode else strategy_fast_guidance() if strategy_mode else {},
        "reference_segments": references,
        "answer": answer,
        "label_result": compact_model_result(label_result) if label_result else {},
        "reply_result": compact_model_result(reply_result),
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def unavailable_bailian_summary(
    run_id: str,
    output_dir: Path,
    question: str,
    context: str,
    image_paths: list[Path],
    image_data: dict[str, Any],
    image_understanding: str,
    error: str,
    mode: str = MODE_BAILIAN_RAG_FAST,
) -> dict[str, Any]:
    return {
        "status": "model_unavailable",
        "mode": mode,
        "error": error,
        "run_id": run_id,
        "question": question,
        "context": context,
        "images": [str(path) for path in image_paths],
        "image_understanding": image_understanding,
        "vision_result": image_data.get("model_result", {}),
        "labels": {},
        "reference_segments": [],
        "answer": {
            "reply": "",
            "coach_analysis": "",
            "labels": {},
            "risk_warning": "百炼 RAG 快速模式还没有配置知识库 ID。",
            "next_step": "",
            "reference_segments": [],
            "debug": {"reason": error},
        },
        "reply_result": {
            "status": "model_unavailable",
            "model": "reply_rag_model",
            "client": "reply_rag_model",
            "error": error,
            "elapsed_seconds": 0,
            "usage": {},
        },
        "output_dir": str(output_dir),
    }


def image_payload(
    question: str,
    context: str,
    image_paths: list[Path],
    models: dict[str, Any],
    user_id: str,
    dry_run: bool,
    vision_style: str = VISION_STYLE_FULL,
) -> dict[str, Any]:
    if not image_paths:
        return {"text": "", "model_result": {}}
    if dry_run:
        return dry_run_image_summary(image_paths)
    return understand_images(question, context, image_paths, models, user_id, style=vision_style)


def vision_style_for_mode(models: dict[str, Any], runtime_mode: str) -> str:
    cfg = models.get("vision_model", {}) if isinstance(models.get("vision_model", {}), dict) else {}
    if runtime_mode in {MODE_BAILIAN_RAG_FAST, MODE_BAILIAN_RAG_STRATEGY_FAST, MODE_BAILIAN_RAG_STRATEGY_QUALITY}:
        return str(cfg.get("fast_prompt_style") or VISION_STYLE_DIALOGUE)
    if runtime_mode == MODE_BAILIAN_RAG_QUALITY:
        return str(cfg.get("quality_prompt_style") or VISION_STYLE_FULL)
    return str(cfg.get("default_prompt_style") or VISION_STYLE_FULL)


def build_input_text(question: str, context: str, image_understanding: str = "") -> str:
    parts = ["用户问题：", question.strip()]
    if context.strip():
        parts.extend(["\n补充背景：", context.strip()])
    if image_understanding.strip():
        parts.extend(["\n截图/图片理解：", IMAGE_INPUT_HINT, image_understanding.strip()])
    return "\n".join(parts)


def build_label_prompt(input_text: str) -> str:
    taxonomy = load_config("taxonomy_v01.json")
    principles = load_config("prompt_principles.json")
    return "\n\n".join(
        [
            load_prompt("reply_label_v01.md"),
            "标签配置：",
            json.dumps(prompt_taxonomy_config(taxonomy), ensure_ascii=False, indent=2),
            "原则：",
            json.dumps(principles, ensure_ascii=False, indent=2),
            "当前输入：",
            input_text,
        ]
    )


def build_quality_label_prompt(input_text: str) -> str:
    taxonomy = load_config("taxonomy_v01.json")
    principles = load_config("prompt_principles.json")
    action_guard = build_frame_action_guard(input_text)
    return "\n\n".join(
        [
            load_prompt("reply_quality_label_v01.md"),
            "标签配置：",
            json.dumps(prompt_taxonomy_config(taxonomy), ensure_ascii=False, indent=2),
            "原则：",
            json.dumps(principles, ensure_ascii=False, indent=2),
            action_guard,
            "当前输入：",
            input_text,
        ]
    )


def build_frame_action_guard(input_text: str) -> str:
    guards: list[str] = []
    if "和谁" in input_text or "跟谁" in input_text:
        guards.append(
            "短人称追问强提醒：当前句只是在索要对象/归属时，回复必须先直给核心对象；"
            "除非上下文明确有第三方，否则不要凭空答第三方，也不要用反问、猜测或吃醋包装替代答案。"
        )
    if any(cue in input_text for cue in ["撩不到", "没机会", "不可能"]):
        guards.append(
            "否定预设强提醒：对方否定你或说你没机会时，不要自我撤退、不要回成自己省事或懒得推进；"
            "优先否定她的预设、拿回筛选权或把互动转成她需要证明的方向。"
        )
    if "表情包" in input_text and "傻" in input_text:
        guards.append(
            "事实纠偏强提醒：对方误以为你在评价她本人时，先纠正评价对象，再轻调侃；"
            "事实纠偏优先于夸可爱、哄人或顺着误会升温。"
        )
    if "上课" in input_text or "偷偷玩" in input_text:
        guards.append(
            "现实状态强提醒：对方在上课或类似场景里想继续玩时，先收住当前干扰，不鼓励她分心；"
            "再给一个低压力、具体的课后/结束后后续钩子，不要只停留在惩罚式角色梗。"
        )
    if "手拉手" in input_text and "操场" in input_text:
        guards.append(
            "方案置换强提醒：对方抛出低价值或太顺手的玩法时，可以拒绝原方案，但要换成更有吸引力的具体方案；"
            "不要只用看表现、够不够格这类空泛筛选结束。"
        )
    if any(cue in input_text for cue in ["出来吃饭", "走 帅哥", "带我吃", "带我去吃"]):
        guards.append(
            "主动邀约强提醒：对方高主动邀约或命令时，不能只说行、走、可以、这顿谁请；"
            "先保留选择权或反客为主，再决定是否给具体方向。"
        )
    if any(cue in input_text for cue in ["太急", "很渣", "显得很渣", "太主动"]):
        guards.append(
            "负面定义强提醒：对方把你定义成太急、太渣或太主动时，不要只反问她怕什么；"
            "回复里要出现自己的选择标准、感觉标准或边界标准。"
        )
    if "分享快乐" in input_text or ("等你" in input_text and "忙" in input_text):
        guards.append(
            "承接投入强提醒：对方表达愿意等你或分享快乐时，先接住这份投入，再让她分享当下具体内容；"
            "不要反过来筛选她够不够甜、够不够有趣、够不够分量。"
        )
    if not guards:
        return ""
    return "当前动作强提醒：\n" + "\n".join(f"- {guard}" for guard in guards)


def build_strategy_label_prompt(input_text: str) -> str:
    action_guard = build_frame_action_guard(input_text)
    return "\n\n".join(
        [
            "你是 Baiou 高框架推拉模式的策略门。只输出合法 JSON，不要 Markdown。",
            "任务：只判断当前这句该用什么高框架动作，不负责写最终回复；策略是动作，不是关系结论，不要依赖案例来决定局势。",
            HIGH_FRAME_SCOPE_RULE,
            HIGH_FRAME_CORE_RULE,
            HIGH_FRAME_FORBID_RULE,
            TEXT_STRUCTURED_INPUT_RULE,
            action_guard,
            f"策略枚举：{'、'.join(STRATEGY_CHOICES)}。",
            "策略区分：暧昧推进用于已有调情、亲密升级、占有玩笑或轻推拉，目标是把气氛推热；"
            "关系框架升级用于对方把推进权抛回、讨论合适/缘分/认真/长期/占多久等关系定义，目标是把问题转成双向关系想象。"
            "高张力推进只作兼容旧类目，能拆到前两类时优先拆。",
            "高张力推进边界：只在对方有明确承接、玩笑空间、暧昧语境或高投入时使用。",
            f"场景类型枚举：{'/'.join(SCENE_TYPE_CHOICES)}。",
            "判断要求：普通接话不要硬标测试；但一旦有推开、筛选、否定、主动命令、关系节奏质疑，要保持框架，不能进入顺从模式。",
            "rag_query 要求：给后续知识库检索一个中文短查询，只保留当前话语动作、场景类型和需要的表达手感；不要列多条，不要写数组，不要加顿号或逗号。",
            "输出结构：",
            json.dumps(
                {
                    "state": {"关系阶段": "", "对方投入度": "", "当前压力": ""},
                    "scene_type": "",
                    "strategy": "",
                    "rag_query": "一个中文检索短语",
                    "reason": "一句话理由",
                    "risk_level": "低/中/高",
                    "forbid": ["不要做的动作"],
                    "style_hint": "松弛/俏皮/暧昧但不油/有边界地推进/降压",
                },
                ensure_ascii=False,
                indent=2,
            ),
            "当前输入：",
            input_text,
        ]
    )


def prompt_taxonomy_config(taxonomy: dict[str, Any]) -> dict[str, Any]:
    output = {"labels": taxonomy.get("labels", {})}
    heat_signals = taxonomy.get("heat_signals", [])
    if isinstance(heat_signals, list) and heat_signals:
        output["heat_signals"] = heat_signals
    return output


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


def build_bailian_rag_prompt(
    input_text: str,
    quality_guidance: dict[str, Any] | None = None,
    strategy_mode: bool = False,
    strategy_guidance: dict[str, Any] | None = None,
) -> str:
    action_guard = build_frame_action_guard(input_text)
    if strategy_guidance:
        return "\n\n".join(
            [
                "你是 Baiou 高框架推拉模式的回复生成器。只输出合法 JSON，不要 Markdown。",
                "【任务与输出】",
                "最终 reply 只能是一句中文短回复，像用户能直接发出去的微信消息；优先 8-24 个汉字，最多一个逗号；不要解释策略，不要写多选项，不要长篇。",
                "【方向：先决定关系动作】",
                HIGH_FRAME_SCOPE_RULE,
                HIGH_FRAME_CORE_RULE,
                "策略门工作方式：上面的 strategy 是唯一决策点，不得反向改变策略；先按策略门确定方向，再写表达。",
                "【表达：把动作写成人话】",
                "高框架不是讲道理：不要把标准、边界、感觉同频写成教练式解释；能用半句拉扯解决，就不要写成论证。",
                "策略适配：strategy 为“关系框架升级”时，主轴是共同想象和关系定义升级；轻筛选只能做尾巴，不能变成交换条件、索取回报或证明。",
                "暧昧奖励：对方索要补偿、奖励、亲亲、陪伴或撒娇时，先给一点甜头/画面感，再轻轻设置条件，避免只有门槛没有情绪价值。",
                "对象调侃：对方提到具体物件、食物、表情、地点、药品时，先抓对象特征做轻损、纠偏或暧昧联想；不要用空泛门槛替代现场感。",
                "轻筛选：可以保留一点门槛和轻上位，但它要服务于暧昧张力和关系想象，像双向游戏，不像资格审查、价值评判、奖惩或逼迫；不要用值不值得、配不配、够不够格把女生写成被评价对象。",
                "后续推进/关系升级引导：当女生承接“合适、缘分、认真、长期”等关系观时，先接住她的价值观，再用当前互动给共同证据，最后落到一个低成本、可互动的小亲密动作，比如称呼、约定、专属感或下次见面的小动作；不要逼迫。",
                "关系框架表达边界：不要把长期、占有或承诺写成合同有效期、审批许可、单方发放资格；门槛可以俏皮，但落点应是共同想象和双向选择。",
                "表达手感：松弛、有框架、有一点暧昧或拉扯；不强怼、不油腻、不羞辱、不装导师。",
                "【边界：什么不能做】",
                HIGH_FRAME_FORBID_RULE,
                "边界：如果策略门或当前输入显示明确停止/不舒服/不要继续，只收住当前推进并轻轻转话题。",
                "输出前自检：如果草稿把女生写成被考核、被交易或被审批对象，或出现看你表现、值不值得、给不给、续期、拿什么换这类语义，必须改写成共同想象、双向选择、长期感或专属感。",
                "【输入规则】",
                TEXT_STRUCTURED_INPUT_RULE,
                action_guard,
                "策略门决策结果：",
                json.dumps(strategy_guidance, ensure_ascii=False, indent=2),
                "【RAG 使用】",
                "知识库使用：百炼 file_search 只找表达参考和人味；当前输入和策略门优先，不照搬案例原句、称呼、强度。",
                "召回降权：如果片段把推进写成考核、交易、审批、价值资格判断，只学习其关系动作，不继承具体表达。",
                "检索软约束：优先只使用策略门 rag_query 作为知识库查询意图；不要把同一意图拆成多条同义查询，也不要扩展成泛泛的高框架、推拉、聊天话术等宽泛查询。",
                "当前输入：",
                input_text,
                "输出结构：",
                json.dumps(
                    {
                        "reply": "一句可直接发送的中文回复",
                        "coach_analysis": "一句话说明用了什么动作",
                        "labels": {
                            "聊天阶段": "",
                            "接触状态": "",
                            "关系推进目标": "",
                            "女生状态": "",
                            "男生目标": "",
                            "推荐策略": "",
                            "风险类型": [],
                            "回复强度": "",
                            "高热度信号": "",
                        },
                        "risk_warning": "",
                        "next_step": "",
                        "reference_segments": [],
                        "debug": {"prompt_version": "high_frame_strategy_quality_v01"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
    if not quality_guidance and not strategy_mode:
        return "\n\n".join(
            [
                "你是 Baiou 日常快速回复助手。只输出合法 JSON，不要 Markdown。",
                DAILY_FAST_SCOPE_RULE,
                DAILY_FAST_CORE_RULE,
                DAILY_FAST_FORBID_RULE,
                "生成要求：最终 reply 只能是一句中文短回复，优先 8-22 个汉字，最多一个逗号；自然、松弛、好接，不输出多选项和解释。",
                "模式区分：遇到明显筛选、推开、挑战、强暧昧、主动邀约拉扯时，不要启动高张力破解，只给低压力承接或轻轻带过；用户要高框架时由策略质量模式处理。",
                TEXT_STRUCTURED_INPUT_RULE,
                action_guard,
                "知识库使用：百炼 file_search 只找日常聊天表达参考；检索围绕对方最后一句、当前话题、情绪状态和轻松接话，不扩展成废物测试、高框架、推拉、进攻。",
                "当前输入：",
                input_text,
                "输出结构：",
                json.dumps(
                    {
                        "reply": "一句可直接发送的中文回复",
                        "coach_analysis": "一句话说明如何低压力接话",
                        "labels": {
                            "聊天阶段": "",
                            "接触状态": "",
                            "关系推进目标": "",
                            "女生状态": "",
                            "男生目标": "",
                            "推荐策略": "",
                            "风险类型": [],
                            "回复强度": "",
                            "高热度信号": "",
                        },
                        "risk_warning": "",
                        "next_step": "",
                        "reference_segments": [],
                        "debug": {"prompt_version": "daily_fast_v01"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
    principles = load_config("prompt_principles.json")
    parts = [
        load_prompt("reply_generate_v01.md"),
        "原则：",
        json.dumps(principles, ensure_ascii=False, indent=2),
        "当前输入：",
        input_text,
    ]
    if quality_guidance:
        parts.extend(
            [
                "当前基础标签与软锚点：",
                json.dumps(quality_guidance, ensure_ascii=False, indent=2),
                "软锚点使用方式：",
                "软锚点用于减少过度解读，不是保守限制。保持自然、有趣、可推进；推进空间低时降低强撩和强邀约，推进空间中/高时可以轻微升温、暧昧试探或边界内的性张力玩笑。",
                TEXT_STRUCTURED_INPUT_RULE,
                FRAME_ACTION_RULE,
                FRAME_ACTION_DETAIL_RULE,
                action_guard,
                RELATIONSHIP_PACE_RULE,
                RELATIONSHIP_PACE_MODE_HINTS["quality"],
                "知识库检索要求：",
                "使用百炼 file_search 从 baiou 片段知识库中检索相似案例。检索词优先围绕女生/对方最后一句、当前句功能、推进尺度、建议手感和关键事实；不要主动加入“废物测试/强框架/反击”等词，除非软锚点判断为明确测试或证据很强。当前截图事实优先于召回片段；召回片段只学习动作和节奏，不继承其强度、称呼或原句。",
                "相似结构化案例片段：",
                "由百炼 file_search 工具返回；如果没有命中，也要基于软锚点和原则给出自然、可推进的回复。",
            ]
        )
    elif strategy_mode:
        parts.extend(
            [
                "策略门实验要求：",
                json.dumps(strategy_fast_guidance(), ensure_ascii=False, indent=2),
                "策略门工作方式：",
                "先在内部完成状态压缩和策略选择，再使用百炼 file_search 从 baiou 片段知识库中检索表达参考。策略是唯一决策点，召回片段只学习说法、节奏和人味，不决定局势、不继承强度、不照搬称呼或原句。",
                "策略选择边界：",
                "低信息、冷淡、防御、拒绝时优先轻承接、轻撤退、转移话题或风险提醒；女生正常/热情且有承接时可以轻推进、轻微调侃或暧昧试探；只有上下文已有玩笑空间、暧昧承接或高投入时，才允许高张力推进。",
                TEXT_STRUCTURED_INPUT_RULE,
                FRAME_ACTION_RULE,
                FRAME_ACTION_DETAIL_RULE,
                action_guard,
                RELATIONSHIP_PACE_RULE,
                RELATIONSHIP_PACE_MODE_HINTS["strategy_fast"],
                "知识库检索要求：",
                "检索词优先围绕女生/对方最后一句、当前句功能、内部选择的策略、建议手感和关键事实；不要让召回片段反向改变策略。当前截图事实优先于召回片段；没有命中也要按策略生成一句自然可发的回复。",
                "当前基础标签：",
                "本模式不预先调用标签模型，请你根据当前输入自行判断并在输出 JSON 的 labels 字段中填写。",
                "输出要求：",
                "最终 reply 只能是一句中文短回复，像用户能直接发出去的微信消息；coach_analysis 可以简短说明内部策略，但不要输出长报告。",
                "相似结构化案例片段：",
                "由百炼 file_search 工具返回；只作为表达参考。",
            ]
        )
    else:
        parts.extend(
            [
                "知识库检索要求：",
                "使用百炼 file_search 从 baiou 片段知识库中检索相似案例。当前截图事实优先于召回片段；召回片段只学习迁移动作、节奏和风险提醒，不继承其强度、称呼或原句。普通撒娇、接话、解释或收尾，不要仅凭单句就主动检索为废物测试或强框架对抗。",
                TEXT_STRUCTURED_INPUT_RULE,
                FRAME_ACTION_RULE,
                FRAME_ACTION_DETAIL_RULE,
                action_guard,
                RELATIONSHIP_PACE_RULE,
                RELATIONSHIP_PACE_MODE_HINTS["fast"],
                "当前基础标签：",
                "本模式不预先调用标签模型，请你根据当前输入自行判断并在输出 JSON 的 labels 字段中填写。",
                "相似结构化案例片段：",
                "由百炼 file_search 工具返回；如果没有命中，也要基于原则给出保守、自然的回复。",
            ]
        )
    return "\n\n".join(parts)


def strategy_fast_guidance() -> dict[str, Any]:
    return {
        "mode": MODE_BAILIAN_RAG_STRATEGY_FAST,
        "decision_rule": "策略优先；RAG 只做表达参考。",
        "strategies": STRATEGY_CHOICES,
        "relationship_pace_rule": RELATIONSHIP_PACE_RULE,
        "aggressive_strategy": {
            "name": "高张力推进",
            "preferred_split": ["暧昧推进", "关系框架升级"],
            "boundary": "只在对方有明确承接、玩笑空间、暧昧语境或高投入时使用；低信息、冷淡、防御、拒绝时禁用。",
        },
    }


def normalize_strategy_guidance(parsed: dict[str, Any], input_text: str = "") -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return heuristic_strategy_guidance(input_text, heuristic_labels(input_text))
    labels = extract_labels(parsed)
    state = parsed.get("state", {}) if isinstance(parsed.get("state", {}), dict) else {}
    scene_type = normalize_choice(parsed.get("scene_type"), SCENE_TYPE_CHOICES)
    strategy = normalize_choice(parsed.get("strategy"), STRATEGY_CHOICES)
    rag_query = normalize_strategy_rag_query(parsed.get("rag_query")) or fallback_strategy_rag_query(input_text, scene_type or "其他", strategy or "轻承接")
    output = {
        "state": {
            "关系阶段": normalize_choice(state.get("关系阶段"), ["刚认识", "破冰期", "熟悉期", "暧昧升温期", "高意向推进期"]),
            "对方投入度": normalize_choice(state.get("对方投入度"), ["低", "中", "高"]),
            "当前压力": normalize_choice(state.get("当前压力"), ["低", "中", "高"]),
            "互动活跃度": normalize_choice(state.get("互动活跃度"), ["低", "中", "高"]),
        },
        "scene_type": scene_type or "其他",
        "strategy": strategy or "轻承接",
        "rag_query": rag_query,
        "reason": str(parsed.get("reason", "")).strip(),
        "risk_level": normalize_choice(parsed.get("risk_level"), ["低", "中", "高"]) or "低",
        "forbid": [str(item).strip() for item in parsed.get("forbid", []) if str(item).strip()] if isinstance(parsed.get("forbid", []), list) else [],
        "style_hint": normalize_choice(parsed.get("style_hint"), ["自然", "松弛", "俏皮", "暧昧但不油", "有边界地推进", "降压"]),
        "labels": labels,
    }
    output["state"] = {key: value for key, value in output["state"].items() if value}
    return {key: value for key, value in output.items() if value not in ("", [], {})}


def normalize_strategy_rag_query(value: Any) -> str:
    raw = value[0] if isinstance(value, list) and value else value
    text = str(raw or "").strip()
    for separator in ["，", "、", ",", ";", "；", "\n", "\r", "\t"]:
        text = text.replace(separator, " ")
    text = " ".join(part for part in text.split() if part)
    return text[:32]


def fallback_strategy_rag_query(input_text: str, scene_type: str, strategy: str) -> str:
    if is_relationship_pace_test(input_text):
        scene_type = "关系节奏测试"
    elif any(cue in input_text for cue in ["出来吃饭", "带我吃", "带我去吃", "走 帅哥"]):
        scene_type = "主动邀约拉扯"
    elif any(cue in input_text for cue in ["撩不到", "没机会", "不可能"]):
        scene_type = "推开否定"
    elif any(cue in input_text for cue in ["和谁", "跟谁"]):
        scene_type = "极短追问"
    return normalize_strategy_rag_query(f"{scene_type} {strategy}")


def heuristic_strategy_guidance(text: str, labels: dict[str, Any]) -> dict[str, Any]:
    female_state = labels.get("女生状态", "")
    if is_relationship_pace_test(text):
        strategy, pressure, style, forbid, scene_type = "轻推进", "中", "有边界地推进", ["顺从式退让", "道歉自证", "长篇解释"], "关系节奏测试"
    elif female_state in {"冷淡", "防御", "拒绝"}:
        strategy, pressure, style, forbid, scene_type = "轻撤退", "高", "降压", ["强撩", "连续追问", "强邀约"], "现实状态边界"
    elif any(word in text for word in ["想你", "想和你聊", "喜欢", "宝宝", "礼物"]):
        strategy, pressure, style, forbid, scene_type = "暧昧试探", "低", "暧昧但不油", ["长篇解释", "过度讨好"], "暧昧进攻"
    elif any(word in text for word in ["嗯嗯", "好的", "知道啦"]):
        strategy, pressure, style, forbid, scene_type = "轻撤退", "中", "自然", ["强行暧昧", "连续追问"], "其他"
    else:
        strategy, pressure, style, forbid, scene_type = "轻承接", "低", "松弛", ["查户口", "长篇大论"], "其他"
    return {
        "state": {
            "关系阶段": labels.get("聊天阶段", "熟悉期"),
            "对方投入度": "中" if is_relationship_pace_test(text) else "低" if female_state in {"冷淡", "低投入", "拒绝"} else "中",
            "当前压力": pressure,
            "互动活跃度": "中",
        },
        "scene_type": scene_type,
        "strategy": strategy,
        "rag_query": fallback_strategy_rag_query(text, scene_type, strategy),
        "reason": "dry-run 启发式策略判断。",
        "risk_level": "中" if pressure == "高" else "低",
        "forbid": forbid,
        "style_hint": style,
        "labels": labels,
    }


def normalize_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if not mode:
        runtime = load_config("web.json").get("runtime", {})
        mode = str(runtime.get("default_mode", MODE_QUALITY_LOCAL)).strip().lower()
    aliases = {
        "quality": MODE_QUALITY_LOCAL,
        "local": MODE_QUALITY_LOCAL,
        "rag": MODE_BAILIAN_RAG_FAST,
        "rag_fast": MODE_BAILIAN_RAG_FAST,
        "rag_quality": MODE_BAILIAN_RAG_QUALITY,
        "bailian_quality": MODE_BAILIAN_RAG_QUALITY,
        "strategy": MODE_BAILIAN_RAG_STRATEGY_FAST,
        "strategy_fast": MODE_BAILIAN_RAG_STRATEGY_FAST,
        "rag_strategy": MODE_BAILIAN_RAG_STRATEGY_FAST,
        "bailian_strategy": MODE_BAILIAN_RAG_STRATEGY_FAST,
        "strategy_quality": MODE_BAILIAN_RAG_STRATEGY_QUALITY,
        "rag_strategy_quality": MODE_BAILIAN_RAG_STRATEGY_QUALITY,
        "bailian_strategy_quality": MODE_BAILIAN_RAG_STRATEGY_QUALITY,
    }
    mode = aliases.get(mode, mode)
    return (
        mode
        if mode in {MODE_QUALITY_LOCAL, MODE_BAILIAN_RAG_FAST, MODE_BAILIAN_RAG_QUALITY, MODE_BAILIAN_RAG_STRATEGY_FAST, MODE_BAILIAN_RAG_STRATEGY_QUALITY}
        else MODE_QUALITY_LOCAL
    )


def resolve_user_id(models: dict[str, Any], mode: str) -> str:
    env_mode = f"BAIOU_PRODUCT_USER_ID_{mode.upper()}"
    env_mode = env_mode.replace("-", "_")
    for name in [env_mode, "BAIOU_PRODUCT_USER_ID"]:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    user_ids = models.get("user_ids", {}) if isinstance(models.get("user_ids"), dict) else {}
    if str(user_ids.get(mode, "")).strip():
        return str(user_ids[mode]).strip()
    if str(user_ids.get("default", "")).strip():
        return str(user_ids["default"]).strip()
    return str(models.get("user_id", "71"))


def quality_label_config(models: dict[str, Any]) -> dict[str, Any]:
    configured = models.get("reply_quality_label_model")
    if isinstance(configured, dict) and configured:
        return configured
    cfg = json.loads(json.dumps(models.get("reply_model") or {}))
    cfg["temperature"] = 0
    cfg["max_tokens"] = min(int(cfg.get("max_tokens", 1200)), 1200)
    cfg["enable_thinking"] = False
    cfg["response_format_json"] = True
    return cfg


def strategy_label_config(models: dict[str, Any]) -> dict[str, Any]:
    configured = models.get("reply_strategy_model")
    if isinstance(configured, dict) and configured:
        return configured
    return quality_label_config(models)


def bailian_rag_config(models: dict[str, Any]) -> tuple[dict[str, Any], str]:
    cfg = json.loads(json.dumps(models.get("reply_rag_model") or {}))
    if not cfg:
        return {}, "reply_rag_model_missing_config"
    file_search = cfg.setdefault("file_search", {})
    vector_ids = configured_vector_store_ids(cfg)
    if not vector_ids:
        return cfg, "reply_rag_model_missing_vector_store_ids"
    file_search["enabled"] = True
    file_search["vector_store_ids"] = vector_ids
    max_num_results = configured_rag_max_num_results(file_search)
    if max_num_results:
        file_search["max_num_results"] = max_num_results
    return cfg, ""


def configured_vector_store_ids(cfg: dict[str, Any]) -> list[str]:
    admin_ids = admin_rag_config().get("vector_store_ids", [])
    if admin_ids:
        return [str(item).strip() for item in admin_ids if str(item).strip()] if isinstance(admin_ids, list) else split_config_list(admin_ids)
    file_search = cfg.get("file_search", {}) if isinstance(cfg.get("file_search"), dict) else {}
    env_name = str(file_search.get("vector_store_ids_env") or cfg.get("vector_store_ids_env") or "").strip()
    raw = os.environ.get(env_name, "") if env_name else ""
    if raw:
        return split_config_list(raw)
    ids = file_search.get("vector_store_ids", [])
    if isinstance(ids, str):
        return split_config_list(ids)
    return [str(item).strip() for item in ids if str(item).strip()] if isinstance(ids, list) else []


def configured_rag_max_num_results(file_search: dict[str, Any]) -> int:
    admin_value = admin_rag_config().get("max_num_results")
    raw = str(admin_value or "").strip()
    if not raw:
        raw = os.environ.get("BAIOU_RAG_MAX_NUM_RESULTS", "").strip()
    if not raw:
        raw = str(file_search.get("max_num_results", "")).strip()
    try:
        value = int(raw)
    except ValueError:
        return 0
    return max(1, min(10, value))


def admin_rag_config() -> dict[str, Any]:
    path = resolve_path(os.environ.get("BAIOU_ADMIN_CONFIG") or "outputs/baiou/product/admin_config.json")
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    rag = payload.get("rag", {}) if isinstance(payload, dict) else {}
    return rag if isinstance(rag, dict) else {}


def split_config_list(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]


def extract_labels(parsed: dict[str, Any]) -> dict[str, Any]:
    labels = parsed.get("labels", parsed)
    if not isinstance(labels, dict):
        return {}
    return normalize_labels(labels)


def normalize_quality_guidance(parsed: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    output = {
        "labels": extract_labels(parsed),
        "当前句功能": normalize_choice(parsed.get("当前句功能"), ["普通接话", "撒娇", "轻微试探", "关系节奏测试", "明确测试", "收尾", "降压"]),
        "推进空间": normalize_choice(parsed.get("推进空间"), ["低", "中", "高"]),
        "推进尺度": normalize_choice(
            parsed.get("推进尺度"),
            ["低压力承接", "轻微调侃", "情绪升温", "暧昧试探", "性张力玩笑", "模糊邀约", "明确邀约", "降压收住"],
        ),
        "建议手感": normalize_choice(parsed.get("建议手感"), ["自然", "松弛", "俏皮", "暧昧但不油", "有边界地推进", "降压"]),
        "判断依据": str(parsed.get("判断依据", "")).strip(),
    }
    return {key: value for key, value in output.items() if value not in ("", [], {})}


def normalize_choice(value: Any, allowed: list[str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in allowed:
        return text
    for item in allowed:
        if item in text or text in item:
            return item
    return text


def heuristic_quality_guidance(text: str, labels: dict[str, Any]) -> dict[str, Any]:
    female_state = labels.get("女生状态", "")
    if is_relationship_pace_test(text):
        function, space, scale, feel = "关系节奏测试", "中", "轻微调侃", "有边界地推进"
    elif female_state in {"冷淡", "防御", "拒绝"}:
        function, space, scale, feel = "降压", "低", "降压收住", "降压"
    elif any(word in text for word in ["嗯嗯", "好的", "先这样", "下次"]):
        function, space, scale, feel = "收尾", "低", "低压力承接", "自然"
    elif any(word in text for word in ["想你", "梦到", "喜欢", "礼物", "想和你聊"]):
        function, space, scale, feel = "撒娇", "中", "情绪升温", "俏皮"
    else:
        function, space, scale, feel = "普通接话", "中", "轻微调侃", "松弛"
    return {
        "labels": labels,
        "当前句功能": function,
        "推进空间": space,
        "推进尺度": scale,
        "建议手感": feel,
        "判断依据": "关系节奏质疑不默认进入顺从模式。" if is_relationship_pace_test(text) else "dry-run 启发式软锚点。",
    }


def normalize_labels(labels: dict[str, Any]) -> dict[str, Any]:
    config = load_config("taxonomy_v01.json")
    taxonomy = config.get("labels", {})
    aliases = merged_label_aliases(config)
    output = {}
    for field, allowed in taxonomy.items():
        value = labels.get(field, [] if field == "风险类型" else "")
        if field == "风险类型":
            if isinstance(value, str):
                value = [value] if value else []
            if not isinstance(value, list):
                value = []
            output[field] = [normalized for item in value for normalized in [normalize_label_value(field, item, allowed, aliases)] if normalized]
        else:
            output[field] = normalize_label_value(field, value, allowed, aliases) or (allowed[0] if allowed else "")
    heat_signals = config.get("heat_signals", ["无"])
    if not isinstance(heat_signals, list):
        heat_signals = ["无"]
    output["高热度信号"] = normalize_label_value("高热度信号", labels.get("高热度信号", ""), heat_signals, aliases) or "无"
    return output


def merged_label_aliases(configured: Any) -> dict[str, dict[str, str]]:
    aliases = json.loads(json.dumps(DEFAULT_LABEL_ALIASES))
    if not isinstance(configured, dict):
        return aliases
    sources = []
    if isinstance(configured.get("aliases"), dict):
        sources.append(configured.get("aliases", {}))
    if isinstance(configured.get("label_aliases"), dict):
        sources.append(configured.get("label_aliases", {}))
    if not sources:
        sources.append(configured)
    for source in sources:
        for field, values in source.items():
            if not isinstance(values, dict):
                continue
            aliases.setdefault(str(field), {}).update({str(key): str(value) for key, value in values.items()})
    return aliases


def normalize_label_value(field: str, value: Any, allowed: list[str], aliases: dict[str, dict[str, str]]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in allowed:
        return text
    field_aliases = aliases.get(field, {})
    for source, target in field_aliases.items():
        if source and source in text and target in allowed:
            return target
    for item in allowed:
        if item and (item in text or text in item):
            return item
    return ""


def has_clear_boundary(text: str) -> bool:
    return any(cue in text for cue in CLEAR_BOUNDARY_CUES)


def is_relationship_pace_test(text: str) -> bool:
    return any(cue in text for cue in RELATIONSHIP_PACE_CUES) and not has_clear_boundary(text)


def heuristic_labels(text: str) -> dict[str, Any]:
    stage = "熟悉期"
    contact_status = "未知"
    relationship_goal = "无"
    heat_signal = "无"
    if any(word in text for word in ["刚加", "刚认识", "匹配", "第一次聊"]):
        stage = "刚认识"
        relationship_goal = "破冰熟悉"
    elif is_invite_context(text):
        stage = "高意向推进期"
        contact_status = "已邀约未见面"
        relationship_goal = "邀约见面"
    elif any(word in text for word in ["想你", "暧昧", "喜欢", "宝宝"]):
        stage = "暧昧升温期"
        relationship_goal = "暧昧升温"
        if "宝宝" in text:
            heat_signal = "亲密称呼"
    if is_relationship_pace_test(text):
        relationship_goal = "暧昧升温"
        heat_signal = "关系想象"

    female_state = "正常"
    if has_clear_boundary(text) or any(word in text for word in ["拒绝", "不想", "算了", "别", "不要"]):
        female_state = "拒绝"
    elif any(word in text for word in ["哈哈", "嗯", "哦", "好吧"]):
        female_state = "低投入"
    elif any(word in text for word in ["主动", "想见", "可以呀", "好啊"]):
        female_state = "热情"

    goal = "延续话题"
    strategy = "话题延展"
    risks: list[str] = []
    strength = "轻松"
    if is_relationship_pace_test(text):
        goal = "升温"
        strategy = "轻微调侃"
        strength = "调侃"
    if stage == "高意向推进期":
        goal = "邀约"
        strategy = "模糊邀约"
    if female_state in {"冷淡", "防御", "拒绝"}:
        goal = "降压"
        strategy = "主动降压"
        relationship_goal = "降压修复"
        strength = "安全"
    if any(word in text for word in ["性张力", "暧昧玩笑", "撩一下"]):
        strategy = "性张力玩笑"
        heat_signal = "性张力玩笑"
    if text.count("?") + text.count("？") >= 2:
        risks.extend(["查户口", "连续追问"])
    if len(text) > 500:
        risks.append("长篇大论")
    return normalize_labels(
        {
            "聊天阶段": stage,
            "接触状态": contact_status,
            "关系推进目标": relationship_goal,
            "女生状态": female_state,
            "男生目标": goal,
            "推荐策略": strategy,
            "风险类型": risks,
            "回复强度": strength,
            "高热度信号": heat_signal,
        }
    )


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
        "高热度信号": item.get("高热度信号", ""),
        "secondary_labels": item.get("secondary_labels", {}),
        "女生最后一句": item.get("女生最后一句", ""),
        "男生原回复": item.get("男生原回复", ""),
        "原回复评价": item.get("原回复评价", ""),
        "更优回复": item.get("更优回复", ""),
        "迁移学习价值": item.get("迁移学习价值", ""),
        "match_reasons": item.get("match_reasons", []),
        "score": item.get("score", 0),
    }


def apply_relationship_pace_label_guard(labels: dict[str, Any], input_text: str = "") -> dict[str, Any]:
    if not labels or not is_relationship_pace_test(input_text):
        return labels
    output = dict(labels)
    output["关系推进目标"] = "暧昧升温"
    output["女生状态"] = "正常"
    output["男生目标"] = "升温"
    if output.get("推荐策略") in {"主动降压", "轻松开场", "话题延展", "明确邀约"}:
        output["推荐策略"] = "情绪升温"
    if output.get("回复强度") == "安全":
        output["回复强度"] = "调侃"
    output["高热度信号"] = output.get("高热度信号") or "无"
    return output


def normalize_reply_result(parsed: dict[str, Any], labels: dict[str, Any], references: list[dict[str, Any]], input_text: str = "") -> dict[str, Any]:
    raw_labels = parsed.get("labels", labels) if isinstance(parsed.get("labels", labels), dict) else labels
    normalized_labels = normalize_labels(raw_labels) if raw_labels else {}
    return {
        "reply": str(parsed.get("reply", "")),
        "coach_analysis": str(parsed.get("coach_analysis", "")),
        "labels": apply_relationship_pace_label_guard(normalized_labels, input_text),
        "risk_warning": str(parsed.get("risk_warning", "")),
        "next_step": str(parsed.get("next_step", "")),
        "reference_segments": parsed.get("reference_segments") if isinstance(parsed.get("reference_segments"), list) else [item.get("segment_id", "") for item in references],
        "debug": parsed.get("debug", {}) if isinstance(parsed.get("debug", {}), dict) else {},
    }


def compact_rag_references(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    for index, item in enumerate(items, start=1):
        refs.append(
            {
                "segment_id": item.get("filename") or item.get("file_id") or f"rag_ref_{index}",
                "file_id": item.get("file_id", ""),
                "filename": item.get("filename", ""),
                "score": item.get("score", ""),
                "text": item.get("text", ""),
                "type": item.get("type", ""),
                "labels": {},
                "secondary_labels": {},
                "match_reasons": ["百炼 file_search 命中"],
            }
        )
    return refs


def compact_model_result(result: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "status": result.get("status", ""),
        "model": result.get("model", ""),
        "client": result.get("client", ""),
        "error": result.get("error", ""),
        "elapsed_seconds": result.get("elapsed_seconds", 0),
        "usage": result.get("usage", {}),
    }
    if result.get("references"):
        compact["references"] = result.get("references", [])
    if result.get("response_debug"):
        compact["response_debug"] = result.get("response_debug", {})
    return compact


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Baiou product reply flow.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--index-path")
    parser.add_argument("--batch-id", default="reply_runs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--mode",
        choices=[MODE_QUALITY_LOCAL, MODE_BAILIAN_RAG_FAST, MODE_BAILIAN_RAG_QUALITY, MODE_BAILIAN_RAG_STRATEGY_FAST, MODE_BAILIAN_RAG_STRATEGY_QUALITY],
    )
    args = parser.parse_args()
    output = json.dumps(
        run_reply(args.question, args.context, args.image, args.index_path, args.batch_id, args.dry_run, args.mode),
        ensure_ascii=False,
        indent=2,
    )
    try:
        print(output)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
