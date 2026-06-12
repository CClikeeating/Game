from baiou.product.runtime.reply_engine import normalize_labels


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
        "女生状态": "热情",
        "男生目标": "升温",
        "推荐策略": "轻微调侃",
        "风险类型": [],
        "回复强度": "调侃",
    }
