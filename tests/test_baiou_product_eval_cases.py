from pathlib import Path

from baiou.product import eval_cases


def test_eval_case_template_declares_product_speaker_rule(tmp_path: Path) -> None:
    target = tmp_path / "eval_cases.json"
    result = eval_cases.write_template(target)
    text = target.read_text(encoding="utf-8")

    assert result["case_count"] == 1
    assert "baiou_product_eval_cases_v01" in text
    assert "left_or_white_is_female_right_or_green_is_male" in text
    assert "bailian_rag_fast" in text
