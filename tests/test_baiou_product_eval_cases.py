import json
from pathlib import Path

from baiou.product.eval import eval_cases
from baiou.product.eval.eval_inputs import build_eval_input, write_eval_inputs


def test_eval_case_template_declares_product_speaker_rule(tmp_path: Path) -> None:
    target = tmp_path / "eval_cases.json"
    result = eval_cases.write_template(target)
    text = target.read_text(encoding="utf-8")

    assert result["case_count"] == 1
    assert "baiou_product_eval_cases_v01" in text
    assert "left_or_white_is_female_right_or_green_is_male" in text
    assert "bailian_rag_fast" in text


def test_product_eval_input_uses_last_male_turn_as_expected_reply() -> None:
    case = build_eval_input(
        {
            "eval_index": 1,
            "case_id": "case_a",
            "segment_id": "seg_a",
            "当前上下文": "\n".join(
                [
                    "turn_0001 女生: ok",
                    "* turn_0002 男生: 那正好，我也在偷闲。",
                    "turn_0003 女生: 我去吃饭了",
                ]
            ),
            "source_turn_ids": ["turn_0002"],
            "女生最后一句": "ok",
            "男生原回复": "那正好，我也在偷闲。",
            "更优回复": "那正好，我也在偷闲。",
        }
    )

    assert case["female_prompt"] == "ok"
    assert case["expected_reply"] == "那正好，我也在偷闲。"
    assert case["expected_reply_source"] == "last_male_turn_block"
    assert case["turn_selection"] == "focused_turns"
    assert "turn_0002 男生" not in case["context"]
    assert "turn_0003 女生" not in case["context"]


def test_product_eval_input_keeps_last_female_turn_as_prompt() -> None:
    case = build_eval_input(
        {
            "eval_index": 2,
            "case_id": "case_b",
            "segment_id": "seg_b",
            "当前上下文": "\n".join(
                [
                    "turn_0001 男生: 晚点去吃点东西",
                    "turn_0002 女生: 和谁",
                ]
            ),
            "女生最后一句": "和谁",
            "男生原回复": "你",
            "更优回复": "保留原回复：“你”",
        }
    )

    assert case["female_prompt"] == "和谁"
    assert case["expected_reply"] == "你"
    assert case["expected_reply_source"] == "better_reply_preserved_quote"
    assert "turn_0002 女生: 和谁" in case["context"]


def test_product_eval_input_keeps_trailing_male_reply_block_together() -> None:
    case = build_eval_input(
        {
            "eval_index": 3,
            "case_id": "case_c",
            "segment_id": "seg_c",
            "当前上下文": "\n".join(
                [
                    "* turn_0001 女生: 那你为啥说喜欢我😅",
                    "* turn_0002 男生: 定律就是",
                    "* turn_0003 男生: 追的太紧 嫌弃粘人",
                    "* turn_0004 男生: 追的不紧 就说不在乎",
                    "* turn_0005 男生: 难搞呀",
                ]
            ),
            "女生最后一句": "那你为啥说喜欢我😅",
            "男生原回复": "定律就是\n追的太紧 嫌弃粘人\n追的不紧 就说不在乎\n难搞呀",
            "更优回复": "定律就是\n追的太紧 嫌弃粘人\n追的不紧 就说不在乎\n难搞呀",
        }
    )

    assert case["female_prompt"] == "那你为啥说喜欢我😅"
    assert case["expected_reply"] == "定律就是\n追的太紧 嫌弃粘人\n追的不紧 就说不在乎\n难搞呀"
    assert case["expected_reply_source"] == "last_male_turn_block"
    assert "turn_0002 男生" not in case["context"]


def test_product_eval_input_flags_prompt_equal_expected_reply() -> None:
    case = build_eval_input(
        {
            "当前上下文": "turn_0001 女生: 好浪漫哦",
            "女生最后一句": "好浪漫哦",
            "男生原回复": "好浪漫哦",
            "更优回复": "好浪漫哦",
        }
    )

    assert case["eval_input_ready"] is False
    assert "expected_reply_matches_female_prompt" in case["eval_input_issues"]


def test_write_product_eval_inputs_from_segments_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "segments.jsonl"
    source.write_text(
        '{"eval_index":1,"case_id":"c","segment_id":"s","当前上下文":"turn_0001 女生: ok\\nturn_0002 男生: 收到","男生原回复":"收到","更优回复":"收到"}\n',
        encoding="utf-8",
    )

    summary = write_eval_inputs(source, tmp_path)

    assert summary["case_count"] == 1
    assert (tmp_path / "product_eval_inputs.jsonl").exists()
    assert (tmp_path / "product_eval_inputs.csv").exists()


def test_write_product_eval_inputs_applies_manual_overrides(tmp_path: Path) -> None:
    source = tmp_path / "segments.jsonl"
    source.write_text(
        "\n".join(
            [
                '{"eval_index":1,"case_id":"c","segment_id":"s1","当前上下文":"turn_0001 女生: 好吧","女生最后一句":"好吧","更优回复":"好吧"}',
                '{"eval_index":6,"case_id":"c","segment_id":"s6","当前上下文":"turn_0001 女生: 你会随叫随到么","女生最后一句":"你会随叫随到么","更优回复":"你会随叫随到么"}',
                '{"eval_index":18,"case_id":"c","segment_id":"s18","当前上下文":"turn_0001 女生: 小越多久下班鸭","女生最后一句":"小越多久下班鸭","更优回复":"小越多久下班鸭"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "product_eval_overrides.json").write_text(
        """{
  "exclude_eval_indices": [1],
  "cases": {
    "6": {"expected_reply": "", "expected_reply_source": "manual_none", "expected_reply_optional": true, "eval_input_ready": true, "eval_input_issues": []},
    "18": {"expected_reply": "别着急想我", "expected_reply_source": "manual_override", "expected_reply_optional": false, "eval_input_ready": true, "eval_input_issues": []}
  }
}""",
        encoding="utf-8",
    )

    summary = write_eval_inputs(source, tmp_path)
    rows_text = (tmp_path / "product_eval_inputs.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in rows_text.splitlines() if line.strip()]

    assert summary["case_count"] == 2
    assert summary["without_expected_reply_count"] == 1
    assert {row["eval_index"] for row in rows} == {6, 18}
    assert any(row["expected_reply"] == "别着急想我" for row in rows)
