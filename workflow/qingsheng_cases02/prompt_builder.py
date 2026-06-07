from __future__ import annotations

import json
from typing import Any


PRIMARY_SYSTEM_PROMPT = """你是 qingsheng skill 案例库的数据标注专家。
你的任务不是聊天回复，而是把完整聊天记录复盘成可训练、可评测的案例 JSON。
必须只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"""


REVIEW_SYSTEM_PROMPT = """你是 qingsheng skill 案例库的复核专家。
你的任务是审查另一个模型对完整聊天案例的判断是否被证据支持。
必须只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"""


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
        ]
        if turn.get("time"):
            parts.append(str(turn["time"]))
        lines.append(f"[{' | '.join(parts)}] {turn.get('text', '')}")
    return "\n".join(lines)


def primary_prompt(case: dict[str, Any], mapping: dict[str, Any]) -> str:
    case_pack = compact_case_for_model(case)
    return f"""下面是一套完整聊天记录，不是局部片段。
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


def review_prompt(case: dict[str, Any], primary_judgment: dict[str, Any], mapping: dict[str, Any]) -> str:
    case_pack = compact_case_for_model(case)
    return f"""下面是一套完整聊天记录，不是局部片段。
这套聊天已经有完整结果。请从完整关系发展回看，复核 DeepSeek 的主判断。
不要只根据最后几句判断阶段。所有不同意项必须引用 turn_id。
阶段不是硬边界，而是连续关系光谱。复核时优先检查 stage_judgment 的 primary_stage、stage_range、strategy_stage 是否合理，不要只争一个单点阶段编号。
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
