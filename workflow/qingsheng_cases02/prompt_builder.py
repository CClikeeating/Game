from __future__ import annotations

import json
from typing import Any


PRIMARY_SYSTEM_PROMPT = """你是 qingsheng skill 案例库的数据标注专家。
你的任务不是聊天回复，而是把完整聊天记录复盘成可训练、可评测的案例 JSON。
必须只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"""


REVIEW_SYSTEM_PROMPT = """你是 qingsheng skill 案例库的复核专家。
你的任务是审查另一个模型对完整聊天案例的判断是否被证据支持。
必须只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"""


FACTUAL_LABEL_RULES = """输入中的 speaker/content_type/visual_note 是管道1给出的事实级标签。管道1只做客观结构化，不判断 IOI/IOD、关系阶段、好坏回复或策略建议。
管道2才负责解释这些事实：女生自拍照可以作为信号候选，但必须结合上下文；表情包主要作为情绪回应参考；男生生活照主要作为男方展示材料；narration 是复盘/讲解材料，可以作为案例参考，但不能当成女方或男方真实聊天发言。"""


CASE_INTERPRETATION_RULES = """这些案例大多是成功案例或至少有可学习点的案例，但截图/长图可能不完整。不要因为缺少前置背景就过度保守，也不要编造没有证据的背景；必须区分“已见证据”和“可能缺失背景”。
阶段是连续光谱，不是硬分类。允许整体主阶段和局部穿插阶段同时存在，例如整体处于阶段4邀约见面，但局部出现阶段6亲密升级/性暗示/身体话题。primary_stage 表示整体大阶段，stage_range 表示跨度，strategy_stage 表示后续建议应采用的策略阶段，cross_stage_signals 记录穿插信号。
请输出 male_profile 作为男生表现画像，但它只能是倾向性参考，不能作为定死的人格判断。分析时关注框架感、引导感、需求感、边界感、幽默感、情绪稳定性和推进节奏；必须引用 turn_id 作为依据，避免因为单句强框架就硬判整体人设。"""


STAGE_BIAS_GUARD = """阶段防偏规则：
1. 这些案例可能大多是成功案例，但不能因为“结果成功”就倒推到阶段6或阶段7。
2. primary_stage 必须由聊天当下的证据决定；strategy_stage 可以比 primary_stage 更进取，但必须说明原因。
3. stage_range 一般不要超过3个连续阶段。只有证据同时覆盖开场、邀约、线下、亲密、确立关系等多个明显阶段时，才允许更宽范围，并必须解释。
4. 阶段7“确立关系”必须有明确关系确认、称呼承诺、排他关系或类似证据。亲密调情、叫老公、幻想、性张力不能单独判为阶段7。
5. 局部高阶段信号应放入 cross_stage_signals，不要直接把整体主阶段硬抬高。"""


GOLD_REFERENCE_RULES = """gold_reference 选择规则：
1. gold_reference 不是自由创作。优先从原案例真实发生的男方回复中选择，不优先模型新写。
2. 优先选择最有可迁移价值的“关键动作”：化解测试、后撤不自证、保持框架、排他性表达、边界感、低需求感、自然邀约、情绪稳定。
3. 不要只因为一句话更暧昧、更刺激、更推进，就把它选为 gold。性张力回复只有在它确实安全化解测试或推进关系时才可选。
4. 如果原案例中存在明显优秀回复，例如“我们之间没有别人”这类排他性/框架表达，必须优先考虑它，而不是换成普通调情句。
5. observed_good_reply 必须引用原案例 turn_id 和原句。next_reply 默认等于 observed_good_reply.quote。
6. 只有原案例完全没有可学习的男方好回复，才允许使用 model_suggested_reply。"""


def compact_case_for_model(case: dict[str, Any], max_turns: int | None = None) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    for block in case.get("blocks", []):
        for turn in block.get("turns", []):
            turns.append(
                {
                    "turn_id": turn.get("turn_id", ""),
                    "block_id": block.get("block_id", turn.get("source_block_id", "")),
                    "speaker": turn.get("speaker", ""),
                    "time": turn.get("time", ""),
                    "text": turn.get("text", ""),
                    "content_type": turn.get("content_type", "text"),
                    "visual_note": turn.get("visual_note", ""),
                    "reason": turn.get("reason", ""),
                    "source_image": turn.get("source_image", ""),
                    "need_review": turn.get("need_review", False),
                }
            )
    if max_turns:
        turns = turns[:max_turns]
    return {
        "case_id": case.get("case_id", ""),
        "summary": case.get("summary", {}),
        "turn_count": len(turns),
        "turns": turns,
    }


def transcript_text(case_pack: dict[str, Any]) -> str:
    lines = [f"# case_id: {case_pack.get('case_id', '')}", ""]
    for turn in case_pack.get("turns", []):
        parts = [
            str(turn.get("turn_id", "")),
            str(turn.get("block_id", "")),
            str(turn.get("speaker", "")),
            str(turn.get("content_type", "text")),
        ]
        if turn.get("time"):
            parts.append(str(turn["time"]))
        visual_note = f"（视觉事实：{turn.get('visual_note')}）" if turn.get("visual_note") else ""
        lines.append(f"[{' | '.join(parts)}] {turn.get('text', '')}{visual_note}")
    return "\n".join(lines)


def format_annotation_memory(annotation_memory: dict[str, Any] | None) -> str:
    if not annotation_memory:
        return ""
    lines = ["项目标注记忆（主模型和复核模型都必须参考；样例不是机械规则）："]
    sections = [
        ("hard_rules", "硬规则"),
        ("preference_rules", "偏好规则"),
        ("example_memory", "样例记忆"),
    ]
    for key, title in sections:
        items = annotation_memory.get(key, []) if isinstance(annotation_memory.get(key, []), list) else []
        if not items:
            continue
        lines.append(f"{title}：")
        for item in items:
            if key == "example_memory":
                lines.append(
                    f"- {item.get('pattern', '')} 例：{item.get('example', '')}。{item.get('note', '')}"
                )
            else:
                lines.append(f"- {item.get('rule', '')}")
    return "\n".join(lines)


def primary_prompt(case: dict[str, Any], mapping: dict[str, Any], annotation_memory: dict[str, Any] | None = None) -> str:
    case_pack = compact_case_for_model(case)
    return f"""{FACTUAL_LABEL_RULES}

{CASE_INTERPRETATION_RULES}

{STAGE_BIAS_GUARD}

{GOLD_REFERENCE_RULES}

{format_annotation_memory(annotation_memory)}

下面是一套完整聊天记录，不是局部片段。
这套聊天已经有完整结果。请从完整关系发展回看，不要只根据最后几句判断阶段。
你需要区分两个视角：
1. retrospective_case_analysis：站在完整案例角度复盘。
2. skill_eval_prompt：模拟用户把聊天发给 qingsheng skill，让 skill 给下一步建议。

所有关键判断必须引用 turn_id。无法判断时设置 need_human_review=true，不要硬编。
阶段不是硬边界，而是连续关系光谱。不要强行只给一个绝对阶段；必须同时给主阶段、阶段范围、策略阶段和模糊原因。
stage_judgment 是阶段判断的主字段；qingsheng_mapping.stage_number/stage_label/stage_confidence 只是兼容旧格式，应与 strategy_stage 保持一致。
为了避免输出过长：stage_evidence 最多 5 条，signals 最多 8 条，turning_points 最多 6 条，good_replies 最多 6 条，bad_replies 最多 6 条，uncertain_items 最多 5 条。
所有模型请求的 user_id 已设置为 0。
重要：gold_reference 不是自由创作题。你必须先从原案例中找出已经真实发生、并且推进关系或化解测试的男方好回复，写入 observed_good_reply。只有原案例没有可学习的好回复时，才把模型新写的回复作为 model_suggested_reply。next_reply 默认应等于 observed_good_reply.quote，而不是另写一句。

qingsheng 标准阶段和信号类型：
{json.dumps(mapping, ensure_ascii=False)}

请输出 JSON，结构必须如下：
{{
  "case_facts": {{
    "relationship_arc": "用中文概括整套关系发展",
    "male_goal": "男方核心目标",
    "male_profile": {{
      "summary": "一句话概括男生整体表现",
      "frame_style": "框架强/框架弱/稳定/被动/过度迎合等，作为倾向参考",
      "leading_style": "主动引导/顺势推进/被动回应/强推等",
      "neediness_level": "low/medium/high",
      "communication_traits": ["幽默", "克制", "边界感", "松弛感"],
      "evidence_turn_ids": ["turn_0001"],
      "confidence": 0.0,
      "caveat": "这是基于当前案例材料的倾向性参考，不是定死判断"
    }},
    "female_state": "女方状态/兴趣水平",
    "outcome": "这套聊天最后实际走向；不知道则写 unknown"
  }},
  "qingsheng_mapping": {{
    "stage_number": 1,
    "stage_label": "阶段1 开场破冰",
    "stage_confidence": 0.0,
    "stage_judgment": {{
      "primary_stage": 1,
      "primary_label": "阶段1 开场破冰",
      "stage_range": [1, 2],
      "strategy_stage": 1,
      "strategy_label": "阶段1 开场破冰",
      "confidence": 0.0,
      "ambiguity_reason": "如果阶段边界模糊，用中文说明为什么，例如处在阶段4到5之间",
      "why_strategy_stage": "为什么后续 skill/eval 应按这个策略阶段处理"
    }},
    "stage_evidence": [{{"turn_id": "turn_0001", "quote": "原句", "why": "为什么支持阶段判断"}}],
    "cross_stage_signals": [{{"from_stage": 4, "to_stage": 6, "turn_id": "turn_0001", "quote": "原句", "why": "整体阶段之外出现的局部高/低阶段信号", "impact_on_strategy": "它如何影响后续策略，但不直接硬改主阶段"}}],
    "signals": [{{"type": "IOI", "turn_id": "turn_0001", "quote": "原句", "interpretation": "解释", "strength": "low/medium/high"}}]
  }},
  "key_moments": {{
    "turning_points": [{{"turn_id": "turn_0001", "quote": "原句", "why_important": "为什么重要"}}],
    "good_replies": [{{"turn_id": "turn_0001", "quote": "男方原句", "why_good": "好在哪里", "transferable_rule": "可迁移规则"}}],
    "bad_replies": [{{"turn_id": "turn_0001", "quote": "男方原句", "why_bad": "不好在哪里", "better_reply": "更好说法"}}]
  }},
  "gold_reference": {{
    "reference_type": "observed_case_reply/model_suggested_reply",
    "observed_good_reply": {{"turn_id": "turn_0001", "quote": "原案例中真实出现的男方好回复", "why_good": "为什么这句值得学", "transferable_rule": "可迁移规则"}},
    "model_suggested_reply": "只有原案例没有可学习好回复时，才填写模型另写回复",
    "next_reply": "优先等于 observed_good_reply.quote；没有真实好回复时才用 model_suggested_reply",
    "why": "为什么这样回",
    "acceptable_alternatives": ["可接受替代回复"],
    "skill_eval_position": "end_of_case"
  }},
  "eval_rubric": {{
    "advisory_must_include": ["必须包含的判断点"],
    "advisory_must_not_include": ["不能出现的错误方向"],
    "autopilot_must_include": ["自动模式必须做到什么"],
    "autopilot_must_not_include": ["自动模式不能出现什么"]
  }},
  "quality": {{
    "need_human_review": false,
    "uncertain_items": [{{"field": "字段路径", "turn_id": "turn_0001", "reason": "为什么不确定", "impact": "如果错了影响什么"}}]
  }}
}}

完整聊天记录：
{transcript_text(case_pack)}
"""


def review_prompt(
    case: dict[str, Any],
    primary_judgment: dict[str, Any],
    mapping: dict[str, Any],
    annotation_memory: dict[str, Any] | None = None,
) -> str:
    case_pack = compact_case_for_model(case)
    return f"""{FACTUAL_LABEL_RULES}

{CASE_INTERPRETATION_RULES}

{STAGE_BIAS_GUARD}

{GOLD_REFERENCE_RULES}

{format_annotation_memory(annotation_memory)}

下面是一套完整聊天记录，不是局部片段。
这套聊天已经有完整结果。请从完整关系发展回看，复核 DeepSeek 的主判断。
不要只根据最后几句判断阶段。所有不同意项必须引用 turn_id。
阶段不是硬边界，而是连续关系光谱。复核时优先检查 stage_judgment 的 primary_stage、stage_range、strategy_stage 是否合理，不要只争一个单点阶段编号。
复核 male_profile 时，只检查它是否是有证据支持的倾向性画像，不要把它当成硬人格标签。复核 cross_stage_signals 时，检查 DeepSeek 是否正确区分整体主阶段和局部穿插阶段。
所有模型请求的 user_id 已设置为 0。
复核 gold_reference 时，要优先检查它是否学习了原案例中真实有效的男方回复；如果模型另写的回复偏离了原案例好回复，请把 observed_good_reply / next_reply 作为冲突项指出。

qingsheng 标准阶段和信号类型：
{json.dumps(mapping, ensure_ascii=False)}

DeepSeek 主判断：
{json.dumps(primary_judgment, ensure_ascii=False)}

请输出 JSON，结构必须如下：
{{
  "verdict": "agree/partial/disagree",
  "stage_review": {{
    "agrees": true,
    "review_stage_number": 1,
    "review_stage_label": "阶段1 开场破冰",
    "review_stage_judgment": {{
      "primary_stage": 1,
      "primary_label": "阶段1 开场破冰",
      "stage_range": [1, 2],
      "strategy_stage": 1,
      "strategy_label": "阶段1 开场破冰",
      "confidence": 0.0,
      "ambiguity_reason": "如果边界模糊，用中文说明",
      "why_strategy_stage": "为什么建议按这个阶段给策略"
    }},
    "reason": "复核理由",
    "evidence_turn_ids": ["turn_0001"]
  }},
  "conflicts": [
    {{
      "field": "字段路径",
      "primary_value": "DeepSeek 的判断",
      "review_value": "你的复核判断",
      "reason": "为什么不同意",
      "evidence_turn_ids": ["turn_0001"],
      "impact": "如果不改会影响什么"
    }}
  ],
  "additional_uncertain_items": [
    {{
      "field": "字段路径",
      "turn_id": "turn_0001",
      "reason": "为什么不确定",
      "impact": "影响什么"
    }}
  ],
  "quality": {{
    "need_human_review": false,
    "notes": "总体复核意见"
  }}
}}

完整聊天记录：
{transcript_text(case_pack)}
"""
