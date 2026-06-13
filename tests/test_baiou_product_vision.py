from baiou.product.runtime import vision_understanding
from baiou.product.runtime.reply_engine import build_input_text


def test_product_vision_prompt_locks_speaker_attribution_contract() -> None:
    system_prompt = vision_understanding.build_system_prompt()
    user_prompt = vision_understanding.build_user_prompt("how reply", "")
    prompt = system_prompt + "\n" + user_prompt

    assert "左侧/白色气泡=女生或对方" in prompt
    assert "右侧/绿色气泡=男生或用户" in prompt
    assert "明确证据" in prompt
    assert "按默认规则归属" in prompt
    assert "说话人归属依据" in prompt
    assert "结构化可见话轮" in prompt
    assert "Markdown 表格" in prompt
    assert "位置/颜色" in prompt
    assert "归属只能写" in prompt
    assert "女生/对方最后一句" in prompt
    assert "男生/用户最近回复" in prompt
    assert "用户真正要回复的位置" in prompt
    assert "当前可见局势" in prompt
    assert "一致性自检" in prompt
    assert "不能跨归属拿句子" in prompt
    assert "male=男生/用户" in prompt
    assert "female=女生/对方" in prompt


def test_product_reply_input_carries_image_reply_position_contract() -> None:
    input_text = build_input_text("怎么回？", "", "女生/对方最后一句：在干嘛")

    assert "截图/图片理解" in input_text
    assert "回复定位要求" in input_text
    assert "程序校正（优先使用）" in input_text
    assert "说话人归属依据" in input_text
    assert "用户真正要回复的位置" in input_text
    assert "左侧/白色气泡=女生或对方" in input_text
    assert "右侧/绿色气泡=男生或用户" in input_text


def test_product_vision_corrects_last_replies_from_structured_turn_table() -> None:
    text = """
2. 结构化可见话轮
| 位置/颜色 | 归属 | 内容类型 | 原文或客观说明 |
|-----------|------|----------|----------------|
| 左侧白色气泡 | 女生/对方 | 文字 | “你想要什么礼物啊” |
| 右侧绿色气泡 | 男生/用户 | 文字 | “哈哈” |
| 右侧绿色气泡 | 男生/用户 | 文字 | “只要你送的 我都喜欢” |
| 左侧白色气泡 | 女生/对方 | 文字 | “哈哈 那我自己看看” |
| 左侧白色气泡 | 女生/对方 | 文字 | “要是送的不对 可不要怪我” |

5. 男生/用户最近回复
“哈哈 那我自己看看”
""".strip()

    corrected = vision_understanding.correct_vision_attribution(text)

    assert "程序校正（优先使用）" in corrected
    assert "女生/对方最后一句：要是送的不对 可不要怪我" in corrected
    assert "男生/用户最近回复：只要你送的 我都喜欢" in corrected
    assert "用户真正要回复的位置：女生/对方最后一句：要是送的不对 可不要怪我" in corrected
