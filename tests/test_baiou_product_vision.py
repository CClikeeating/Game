from baiou.product.runtime import vision_understanding


def test_product_vision_prompt_locks_speaker_attribution_contract() -> None:
    system_prompt = vision_understanding.build_system_prompt()
    user_prompt = vision_understanding.build_user_prompt("how reply", "")
    prompt = system_prompt + "\n" + user_prompt

    assert "左侧/白色气泡=女生或对方" in prompt
    assert "右侧/绿色气泡=男生或用户" in prompt
    assert "明确证据" in prompt
    assert "说话人归属依据" in prompt
    assert "女生/对方最后一句" in prompt
    assert "男生/用户最近回复" in prompt
