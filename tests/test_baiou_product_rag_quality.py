from baiou.product.runtime.reply_engine import (
    MODE_BAILIAN_RAG_QUALITY,
    build_bailian_rag_prompt,
    build_quality_label_prompt,
    normalize_mode,
    normalize_quality_guidance,
    resolve_user_id,
)


def test_bailian_rag_quality_mode_and_user_id_are_configurable(monkeypatch) -> None:
    models = {
        "user_id": "71",
        "user_ids": {"default": "71", MODE_BAILIAN_RAG_QUALITY: "72"},
    }

    assert normalize_mode("rag_quality") == MODE_BAILIAN_RAG_QUALITY
    assert resolve_user_id(models, MODE_BAILIAN_RAG_QUALITY) == "72"

    monkeypatch.setenv("BAIOU_PRODUCT_USER_ID_BAILIAN_RAG_QUALITY", "88")
    assert resolve_user_id(models, MODE_BAILIAN_RAG_QUALITY) == "88"


def test_quality_guidance_is_lightweight_soft_anchor() -> None:
    guidance = normalize_quality_guidance(
        {
            "labels": {"聊天阶段": "初识", "女生状态": "正常", "男生目标": "延续话题", "推荐策略": "轻微调侃", "风险类型": [], "回复强度": "中"},
            "当前句功能": "普通撒娇",
            "推进空间": "中等",
            "推进尺度": "情绪升温/暧昧试探",
            "建议手感": "俏皮一点",
            "判断依据": "女生愿意继续聊，但没有强测试证据。",
        }
    )

    assert guidance["labels"]["聊天阶段"] == "刚认识"
    assert guidance["labels"]["接触状态"] == "未知"
    assert guidance["labels"]["关系推进目标"] == "无"
    assert guidance["labels"]["高热度信号"] == "无"
    assert guidance["当前句功能"] == "撒娇"
    assert guidance["推进空间"] == "中"
    assert guidance["推进尺度"] == "情绪升温"
    assert guidance["建议手感"] == "俏皮"


def test_bailian_quality_prompt_uses_soft_anchor_without_overconstraining() -> None:
    prompt = build_bailian_rag_prompt(
        "用户问题：\n我该怎么回",
        {
            "labels": {"聊天阶段": "熟悉期"},
            "当前句功能": "撒娇",
            "推进空间": "中",
            "推进尺度": "情绪升温",
            "建议手感": "俏皮",
            "判断依据": "女生轻松接话。",
        },
    )

    assert "当前基础标签与软锚点" in prompt
    assert "软锚点用于减少过度解读，不是保守限制" in prompt
    assert "保持自然、有趣、可推进" in prompt
    assert "性张力玩笑" in prompt
    assert "女生/对方最后一句、当前句功能、推进尺度、建议手感" in prompt
    assert "除非软锚点判断为明确测试或证据很强" in prompt
    assert "那聊点付费的" in prompt
    assert "少用“奖励你”“给你机会”“乖”等训导感词" in prompt
    assert "女生只回复“嗯嗯/好/好的/知道啦”等低信息量承接" in prompt
    assert "不要强行解读为暧昧、口是心非、怕你担心" in prompt


def test_quality_label_prompt_does_not_overread_low_information_acknowledgement() -> None:
    prompt = build_quality_label_prompt("女生/对方最后一句：嗯嗯\n男生/用户最近回复：那你少喝点 早点回去")

    assert "低信息量承接" in prompt
    assert "不要强行解读为暧昧、口是心非、怕你担心" in prompt
    assert "推进空间优先为低" in prompt
    assert "推进尺度优先为低压力承接或降压收住" in prompt


def test_quality_guidance_accepts_chat_level_sexual_tension_scale() -> None:
    guidance = normalize_quality_guidance(
        {
            "labels": {
                "聊天阶段": "暧昧升温期",
                "接触状态": "已线下接触",
                "关系推进目标": "亲密升级推进",
                "女生状态": "热情",
                "男生目标": "升温",
                "推荐策略": "性张力玩笑",
                "风险类型": [],
                "回复强度": "暧昧",
                "高热度信号": "性张力玩笑",
            },
            "当前句功能": "轻微试探",
            "推进空间": "高",
            "推进尺度": "性张力玩笑",
            "建议手感": "暧昧但不油",
            "判断依据": "女生接梗且语境接受玩笑。",
        }
    )

    assert guidance["推进尺度"] == "性张力玩笑"
    assert guidance["建议手感"] == "暧昧但不油"
    assert guidance["labels"]["推荐策略"] == "性张力玩笑"
    assert guidance["labels"]["高热度信号"] == "性张力玩笑"
