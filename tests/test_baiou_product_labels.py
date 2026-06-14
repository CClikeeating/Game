from baiou.product.runtime.reply_engine import build_label_prompt, build_quality_label_prompt, normalize_labels


def test_normalize_labels_maps_model_aliases_to_taxonomy() -> None:
    labels = normalize_labels(
        {
            "聊天阶段": "暧昧升温",
            "女生状态": "热情/试探",
            "男生目标": "维持框架/轻微推拉",
            "推荐策略": "轻微调侃/挑战",
            "风险类型": [],
            "回复强度": "中",
        }
    )

    assert labels == {
        "聊天阶段": "暧昧升温期",
        "接触状态": "未知",
        "关系推进目标": "无",
        "女生状态": "热情",
        "男生目标": "升温",
        "推荐策略": "轻微调侃",
        "风险类型": [],
        "回复强度": "调侃",
        "高热度信号": "无",
    }


def test_normalize_labels_keeps_v02_fields_and_aliases() -> None:
    labels = normalize_labels(
        {
            "聊天阶段": "邀约期",
            "接触状态": "已线下接触",
            "关系推进目标": "性关系",
            "女生状态": "热情",
            "男生目标": "升温",
            "推荐策略": "性张力",
            "风险类型": ["性张力玩笑", "油腻"],
            "回复强度": "暧昧",
            "高热度信号": "亲密升级",
        }
    )

    assert labels["聊天阶段"] == "高意向推进期"
    assert labels["接触状态"] == "已线下接触"
    assert labels["关系推进目标"] == "性关系推进"
    assert labels["推荐策略"] == "性张力玩笑"
    assert labels["风险类型"] == ["油腻"]
    assert labels["高热度信号"] == "亲密升级信号"


def test_product_label_prompts_use_v02_taxonomy_without_old_output_stage() -> None:
    prompt = build_label_prompt("用户问题：怎么回")
    quality_prompt = build_quality_label_prompt("用户问题：怎么回")

    for text in [prompt, quality_prompt]:
        assert "高意向推进期" in text
        assert "接触状态" in text
        assert "关系推进目标" in text
        assert "高热度信号" in text
        assert "性张力玩笑" in text
        assert "邀约期" not in text
