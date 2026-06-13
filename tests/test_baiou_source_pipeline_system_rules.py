from baiou.source_pipeline.apply_human_review import parse_manual_turns
from baiou.source_pipeline.run_pipeline import should_be_system


def test_source_pipeline_system_text_rules() -> None:
    rules = {
        "system_text_exact": ["以上是打招呼的内容"],
        "system_text_contains": ["你已添加了，现在可以开始聊天了"],
        "system_time_patterns": [r"^星期[一二三四五六日天]\s*(上午|下午|晚上)?\s*\d{1,2}:\d{2}$"],
    }

    assert should_be_system("以上是打招呼的内容", rules)
    assert should_be_system("你已添加了，现在可以开始聊天了。", rules)
    assert should_be_system("星期二 下午10:04", rules)
    assert not should_be_system("女生说晚上10:04见", rules)


def test_manual_review_transcript_parses_system_time_lines() -> None:
    turns = parse_manual_turns(
        "\n".join(
            [
                "男：刚才我睡着了",
                "系统时间：2020年1月27日下午5:42",
                "女：那你说怎么补偿我",
                "星期二 下午10:04",
                "男给你个大亲亲",
            ]
        ),
        "unknown",
    )

    assert [turn["speaker"] for turn in turns] == ["male", "system", "female", "system", "male"]
    assert turns[-1]["text"] == "给你个大亲亲"
