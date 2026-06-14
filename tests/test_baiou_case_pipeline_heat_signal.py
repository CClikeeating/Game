from baiou.case_pipeline.schema import normalize_segment, validate_segments


def base_segment(**overrides: object) -> dict:
    segment = {
        "segment_id": "seg_001",
        "source_turn_ids": ["turn_0001"],
        "当前上下文": "女生接梗并继续互动，男生用轻度暧昧意象升温。",
        "女生最后一句": "你想得美",
        "男生原回复": "那我想得认真一点",
        "原回复评价": "有效：女生接梗时轻度升温。",
        "聊天阶段": "暧昧升温期",
        "接触状态": "未线下见面",
        "关系推进目标": "暧昧升温",
        "女生状态": "热情",
        "男生目标": "升温",
        "推荐策略": "性张力玩笑",
        "风险类型": ["性张力玩笑", "油腻"],
        "回复强度": "暧昧",
        "高热度信号": "性张力玩笑",
        "次要标签": {},
        "更优回复": "保留原回复：那我想得认真一点",
        "迁移学习价值": "女生接梗时可用轻度性张力玩笑升温，但不施压。",
    }
    segment.update(overrides)
    return segment


def test_sexual_tension_joke_is_strategy_not_risk() -> None:
    segment = normalize_segment(base_segment(), "case_001", 1)

    assert segment["推荐策略"] == "性张力玩笑"
    assert segment["风险类型"] == ["油腻"]
    assert segment["高热度信号"] == "性张力玩笑"
    assert not validate_segments([segment])


def test_heat_signal_defaults_to_none_for_missing_or_invalid_values() -> None:
    missing = normalize_segment(base_segment(**{"高热度信号": ""}), "case_001", 1)
    invalid = normalize_segment(base_segment(**{"高热度信号": "不存在的信号"}), "case_001", 1)

    assert missing["高热度信号"] == "无"
    assert invalid["高热度信号"] == "无"


def test_v02_aliases_and_new_fields_are_normalized() -> None:
    segment = normalize_segment(
        base_segment(
            **{
                "聊天阶段": "邀约期",
                "接触状态": "已线下接触",
                "关系推进目标": "性关系推进",
                "推荐策略": "暧昧试探",
                "高热度信号": "亲密升级",
            }
        ),
        "case_001",
        1,
    )

    assert segment["聊天阶段"] == "高意向推进期"
    assert segment["接触状态"] == "已线下接触"
    assert segment["关系推进目标"] == "性关系推进"
    assert segment["推荐策略"] == "暧昧试探"
    assert segment["高热度信号"] == "亲密升级信号"
    assert not validate_segments([segment])
