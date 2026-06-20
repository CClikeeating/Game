import json

from baiou.product.runtime.reply_engine import (
    MODE_BAILIAN_RAG_FAST,
    MODE_BAILIAN_RAG_QUALITY,
    MODE_BAILIAN_RAG_STRATEGY_FAST,
    MODE_BAILIAN_RAG_STRATEGY_QUALITY,
    bailian_rag_config,
    build_bailian_rag_prompt,
    build_strategy_label_prompt,
    build_quality_label_prompt,
    heuristic_labels,
    heuristic_quality_guidance,
    heuristic_strategy_guidance,
    normalize_mode,
    normalize_quality_guidance,
    normalize_strategy_guidance,
    normalize_reply_result,
    resolve_user_id,
    vision_style_for_mode,
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


def test_bailian_rag_strategy_fast_is_configurable_without_replacing_existing_modes(monkeypatch) -> None:
    models = {
        "user_id": "71",
        "user_ids": {"default": "71", MODE_BAILIAN_RAG_STRATEGY_FAST: "73"},
    }

    assert normalize_mode("strategy_fast") == MODE_BAILIAN_RAG_STRATEGY_FAST
    assert normalize_mode("bailian_rag_strategy_fast") == MODE_BAILIAN_RAG_STRATEGY_FAST
    assert normalize_mode("strategy_quality") == MODE_BAILIAN_RAG_STRATEGY_QUALITY
    assert normalize_mode("bailian_rag_strategy_quality") == MODE_BAILIAN_RAG_STRATEGY_QUALITY
    assert normalize_mode("rag_fast") == MODE_BAILIAN_RAG_FAST
    assert normalize_mode("rag_quality") == MODE_BAILIAN_RAG_QUALITY
    assert resolve_user_id(models, MODE_BAILIAN_RAG_STRATEGY_FAST) == "73"

    monkeypatch.setenv("BAIOU_PRODUCT_USER_ID_BAILIAN_RAG_STRATEGY_FAST", "89")
    assert resolve_user_id(models, MODE_BAILIAN_RAG_STRATEGY_FAST) == "89"


def test_bailian_rag_max_num_results_is_configurable(monkeypatch) -> None:
    models = {
        "reply_rag_model": {
            "file_search": {
                "vector_store_ids": ["vs_1"],
                "max_num_results": 3,
            }
        }
    }

    cfg, error = bailian_rag_config(models)
    assert error == ""
    assert cfg["file_search"]["max_num_results"] == 3

    monkeypatch.setenv("BAIOU_RAG_MAX_NUM_RESULTS", "5")
    cfg, error = bailian_rag_config(models)
    assert error == ""
    assert cfg["file_search"]["max_num_results"] == 5


def test_fast_and_strategy_modes_use_short_vision_prompt_but_quality_keeps_full_prompt() -> None:
    models = {"vision_model": {}}

    assert vision_style_for_mode(models, MODE_BAILIAN_RAG_FAST) == "dialogue"
    assert vision_style_for_mode(models, MODE_BAILIAN_RAG_STRATEGY_FAST) == "dialogue"
    assert vision_style_for_mode(models, MODE_BAILIAN_RAG_STRATEGY_QUALITY) == "dialogue"
    assert vision_style_for_mode(models, MODE_BAILIAN_RAG_QUALITY) == "full"


def test_admin_config_overrides_rag_file_search(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "admin_config.json"
    config_path.write_text(json.dumps({"rag": {"vector_store_ids": ["admin_store"], "max_num_results": 4}}), encoding="utf-8")
    monkeypatch.setenv("BAIOU_ADMIN_CONFIG", str(config_path))
    monkeypatch.setenv("BAIOU_VECTOR_STORE_IDS", "env_store")
    monkeypatch.setenv("BAIOU_RAG_MAX_NUM_RESULTS", "5")
    models = {
        "reply_rag_model": {
            "file_search": {
                "vector_store_ids_env": "BAIOU_VECTOR_STORE_IDS",
                "vector_store_ids": ["model_store"],
                "max_num_results": 3,
            }
        }
    }

    cfg, error = bailian_rag_config(models)

    assert error == ""
    assert cfg["file_search"]["vector_store_ids"] == ["admin_store"]
    assert cfg["file_search"]["max_num_results"] == 4


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


def test_strategy_fast_prompt_keeps_rag_as_expression_reference() -> None:
    prompt = build_bailian_rag_prompt("用户问题：\n我该怎么回", strategy_mode=True)

    assert "策略门实验要求" in prompt
    assert "策略是唯一决策点" in prompt
    assert "召回片段只学习说法、节奏和人味" in prompt
    assert "不要让召回片段反向改变策略" in prompt
    assert "高张力推进" in prompt
    assert "只在对方有明确承接、玩笑空间、暧昧语境或高投入时使用" in prompt
    assert "最终 reply 只能是一句中文短回复" in prompt


def test_daily_fast_prompt_is_slim_low_pressure_chat_mode() -> None:
    prompt = build_bailian_rag_prompt("用户问题：\n女生/对方最后一句：今天好累")

    assert "日常快速回复助手" in prompt
    assert "安全无压力" in prompt
    assert "接话" in prompt
    assert "话题" in prompt
    assert "轻微暧昧" in prompt
    assert "策略质量模式" in prompt
    assert "daily_fast_v01" in prompt
    assert "只找日常聊天表达参考" in prompt
    assert "高框架推拉模式的回复生成器" not in prompt
    assert "策略门决策结果" not in prompt
    assert "当前基础标签与软锚点" not in prompt


def test_strategy_quality_prompt_uses_explicit_strategy_as_decision_point() -> None:
    strategy_prompt = build_strategy_label_prompt("用户问题：\n我该怎么回")
    reply_prompt = build_bailian_rag_prompt(
        "用户问题：\n我该怎么回",
        strategy_guidance={
            "state": {"关系阶段": "熟悉期", "对方投入度": "中", "当前压力": "低", "互动活跃度": "中"},
            "strategy": "暧昧试探",
            "rag_query": "暧昧试探 短回复",
            "reason": "对方有承接，可以轻微升温。",
            "risk_level": "低",
            "forbid": ["长篇解释"],
            "style_hint": "暧昧但不油",
        },
    )

    assert "策略是动作，不是关系结论" in strategy_prompt
    assert "不要依赖案例来决定局势" in strategy_prompt
    assert "高张力推进边界" in strategy_prompt
    assert "rag_query 要求" in strategy_prompt
    assert "一个中文检索短语" in strategy_prompt
    assert "策略门决策结果" in reply_prompt
    assert "上面的 strategy 是唯一决策点" in reply_prompt
    assert "不得反向改变策略" in reply_prompt
    assert "优先只使用策略门 rag_query" in reply_prompt
    assert "不要把同一意图拆成多条同义查询" in reply_prompt
    assert "最终 reply 只能是一句中文短回复" in reply_prompt
    for section in ["【任务与输出】", "【方向：先决定关系动作】", "【表达：把动作写成人话】", "【边界：什么不能做】", "【输入规则】", "【RAG 使用】"]:
        assert section in reply_prompt
        assert section not in strategy_prompt


def test_strategy_quality_prompt_keeps_push_playful_without_pressure() -> None:
    strategy_prompt = build_strategy_label_prompt("用户问题：\n我该怎么回")
    reply_prompt = build_bailian_rag_prompt(
        "用户问题：\n我该怎么回",
        strategy_guidance={
            "strategy": "暧昧试探",
            "rag_query": "暧昧拉扯 短回复",
            "risk_level": "低",
            "style_hint": "暧昧但不油",
        },
    )
    daily_prompt = build_bailian_rag_prompt("用户问题：\n我该怎么回")

    for prompt in [strategy_prompt, reply_prompt]:
        assert "当女生把推进权抛回来时" in prompt
        assert "不要把回复写成“女生需要证明自己”" in prompt
        assert "不要把轻门槛落成“看你表现”一类单向筛选" in prompt
        assert "临时还是长期、表面便宜还是真正喜欢、占有感还是双向选择" in prompt
        assert "要先给情绪价值和关系想象" in prompt
        assert "不要变成审查、要挟或价值资格评判" in prompt
        assert "表现好就续期" not in prompt

    assert "当女生把推进权抛回来时" not in daily_prompt


def test_strategy_quality_reply_prompt_guides_relationship_value_followup() -> None:
    reply_prompt = build_bailian_rag_prompt(
        "用户问题：\n我该怎么回",
        strategy_guidance={
            "strategy": "暧昧试探",
            "rag_query": "关系观承接 短回复",
            "risk_level": "低",
            "style_hint": "暧昧但不油",
        },
    )
    daily_prompt = build_bailian_rag_prompt("用户问题：\n我该怎么回")

    assert "后续推进" in reply_prompt
    assert "合适、缘分、认真、长期" in reply_prompt
    assert "先接住她的价值观" in reply_prompt
    assert "当前互动给共同证据" in reply_prompt
    assert "低成本、可互动的小亲密动作" in reply_prompt
    assert "称呼、约定、专属感或下次见面的小动作" in reply_prompt
    assert "不要逼迫" in reply_prompt
    assert "后续推进" not in daily_prompt


def test_strategy_gate_splits_high_tension_into_push_and_relationship_frame() -> None:
    strategy_prompt = build_strategy_label_prompt("女生/对方最后一句：那就要看你想让我占多久了")

    assert "暧昧推进" in strategy_prompt
    assert "关系框架升级" in strategy_prompt
    assert "能拆到前两类时优先拆" in strategy_prompt
    assert "对方把推进权抛回" in strategy_prompt
    assert "双向关系想象" in strategy_prompt


def test_strategy_guidance_preserves_relationship_frame_upgrade() -> None:
    guidance = normalize_strategy_guidance(
        {
            "scene_type": "关系框架升级",
            "strategy": "关系框架升级",
            "rag_query": "关系框架升级 长期想象 短回复",
            "risk_level": "低",
            "style_hint": "暧昧但不油",
        },
        "女生/对方最后一句：那就要看你想让我占多久了",
    )

    assert guidance["scene_type"] == "关系框架升级"
    assert guidance["strategy"] == "关系框架升级"
    assert guidance["rag_query"] == "关系框架升级 长期想象 短回复"


def test_strategy_quality_reply_prompt_keeps_light_screening_and_relationship_upgrade_guidance() -> None:
    reply_prompt = build_bailian_rag_prompt(
        "女生/对方最后一句：如果合适的话，为什么不呢",
        strategy_guidance={
            "scene_type": "关系框架升级",
            "strategy": "关系框架升级",
            "rag_query": "关系框架升级 低成本亲密动作",
            "risk_level": "低",
            "style_hint": "暧昧但不油",
        },
    )
    daily_prompt = build_bailian_rag_prompt("女生/对方最后一句：如果合适的话，为什么不呢")

    assert "轻筛选" in reply_prompt
    assert "strategy 为“关系框架升级”" in reply_prompt
    assert "主轴是共同想象和关系定义升级" in reply_prompt
    assert "交换条件、索取回报或证明" in reply_prompt
    assert "像双向游戏" in reply_prompt
    assert "价值评判" in reply_prompt
    assert "值不值得、配不配、够不够格" in reply_prompt
    assert "被评价对象" in reply_prompt
    assert "关系升级引导" in reply_prompt
    assert "合同有效期" in reply_prompt
    assert "审批许可" in reply_prompt
    assert "单方发放资格" in reply_prompt
    assert "共同想象和双向选择" in reply_prompt
    assert "输出前自检" in reply_prompt
    assert "被考核、被交易或被审批对象" in reply_prompt
    assert "看你表现、值不值得、给不给、续期、拿什么换" in reply_prompt
    assert "召回降权" in reply_prompt
    assert "不继承具体表达" in reply_prompt
    assert "称呼、约定、专属感或下次见面的小动作" in reply_prompt
    assert "轻筛选" not in daily_prompt
    assert "关系升级引导" not in daily_prompt


def test_strategy_guidance_preserves_single_rag_query_soft_constraint() -> None:
    guidance = normalize_strategy_guidance(
        {
            "state": {"关系阶段": "熟悉期", "对方投入度": "中", "当前压力": "低"},
            "scene_type": "主动邀约拉扯",
            "strategy": "高张力推进",
            "rag_query": ["主动邀约拉扯，反客为主，短回复"],
            "reason": "对方主动邀约，需要保留选择权。",
            "risk_level": "低",
            "forbid": ["直接答应"],
            "style_hint": "俏皮",
        },
        "女生/对方最后一句：走 帅哥 出来吃饭",
    )

    assert guidance["scene_type"] == "主动邀约拉扯"
    assert guidance["rag_query"] == "主动邀约拉扯 反客为主 短回复"
    assert "，" not in guidance["rag_query"]


def test_strategy_guidance_adds_fallback_rag_query_when_missing() -> None:
    guidance = normalize_strategy_guidance(
        {
            "scene_type": "其他",
            "strategy": "轻推进",
            "risk_level": "低",
        },
        "女生/对方最后一句：我觉得我们是不是太快了",
    )

    assert guidance["scene_type"] == "其他"
    assert guidance["rag_query"] == "关系节奏测试 轻推进"


def test_quality_label_prompt_does_not_overread_low_information_acknowledgement() -> None:
    prompt = build_quality_label_prompt("女生/对方最后一句：嗯嗯\n男生/用户最近回复：那你少喝点 早点回去")

    assert "低信息量承接" in prompt
    assert "不要强行解读为暧昧、口是心非、怕你担心" in prompt
    assert "推进空间优先为低" in prompt
    assert "推进尺度优先为低压力承接或降压收住" in prompt


def test_relationship_pace_prompt_blocks_compliance_mode() -> None:
    quality_prompt = build_quality_label_prompt("女生/对方最后一句：我觉得我们是不是太快了")
    strategy_prompt = build_strategy_label_prompt("女生/对方最后一句：我们才认识几天就在一起了")
    fast_prompt = build_bailian_rag_prompt("女生/对方最后一句：我觉得我们发展太快了", strategy_mode=True)

    for prompt in [quality_prompt, strategy_prompt, fast_prompt]:
        assert "关系节奏" in prompt
        assert "不能进入顺从模式" in prompt
        assert "好，听你的" in prompt
        assert "按你的节奏来" in prompt
        assert "快慢不重要" in prompt
        assert "表面维度" in prompt
        assert "背后担忧" in prompt
        assert "更高层标准" in prompt
        assert "不要固定输出同一句" in prompt
        assert "男生目标=降压" in prompt


def test_text_structured_input_and_speech_act_rules_are_shared() -> None:
    fast_prompt = build_bailian_rag_prompt("文本评测入口：\nturn_0001 女生: 和谁", strategy_mode=True)
    quality_prompt = build_bailian_rag_prompt(
        "文本评测入口：\nturn_0001 女生: 和谁",
        {
            "labels": {"聊天阶段": "熟悉期"},
            "当前句功能": "轻微试探",
            "推进空间": "中",
            "推进尺度": "轻微调侃",
            "建议手感": "松弛",
        },
    )

    for prompt in [fast_prompt, quality_prompt]:
        assert "文本结构输入规则" in prompt
        assert "禁止要求用户再上传截图" in prompt
        assert "话语动作优先于字面接话" in prompt
        assert "极短追问优先极短直给" in prompt
        assert "主动邀约或命令不必总是立即接受" in prompt
        assert "动作子规则要可迁移" in prompt
        assert "先直给核心信息" in prompt
        assert "不要凭空引入第三方" in prompt
        assert "反客为主" in prompt
        assert "误读你评价的对象" in prompt
        assert "选择感、感觉、投入一致性和自有边界" in prompt
        assert "否定她的预设" in prompt
        assert "事实纠偏优先级高于夸奖和哄" in prompt
        assert "当前动作强提醒" in prompt
        assert "短人称追问强提醒" in prompt


def test_dynamic_action_guard_is_added_to_quality_and_strategy_prompts() -> None:
    quality_prompt = build_quality_label_prompt("女生/对方最后一句：我就发了个表情包 就傻了？哪里傻")
    strategy_prompt = build_strategy_label_prompt("女生/对方最后一句：走 帅哥 出来吃饭")

    assert "事实纠偏强提醒" in quality_prompt
    assert "事实纠偏优先于夸可爱" in quality_prompt
    assert "主动邀约强提醒" in strategy_prompt
    assert "不能只说行、走、可以、这顿谁请" in strategy_prompt


def test_relationship_pace_heuristics_keep_frame_without_overriding_boundary() -> None:
    text = "女生/对方最后一句：我觉得我们是不是太快了，我们才认识几天就在一起了"
    labels = heuristic_labels(text)
    quality = heuristic_quality_guidance(text, labels)
    strategy = heuristic_strategy_guidance(text, labels)

    assert labels["女生状态"] == "正常"
    assert labels["男生目标"] == "升温"
    assert labels["推荐策略"] == "轻微调侃"
    assert quality["当前句功能"] == "关系节奏测试"
    assert quality["推进空间"] == "中"
    assert quality["推进尺度"] == "轻微调侃"
    assert strategy["strategy"] == "轻推进"
    assert "顺从式退让" in strategy["forbid"]

    boundary_labels = heuristic_labels("女生/对方最后一句：我不舒服，先别推进了")
    boundary_quality = heuristic_quality_guidance("女生/对方最后一句：我不舒服，先别推进了", boundary_labels)

    assert boundary_labels["女生状态"] == "拒绝"
    assert boundary_labels["男生目标"] == "降压"
    assert boundary_labels["推荐策略"] == "主动降压"
    assert boundary_quality["当前句功能"] == "降压"


def test_relationship_pace_final_labels_are_guarded_from_compliance_mode() -> None:
    answer = normalize_reply_result(
        {
            "reply": "你担心的是节奏，还是节奏背后的确定感？",
            "labels": {
                "聊天阶段": "暧昧升温期",
                "关系推进目标": "降压修复",
                "女生状态": "防御",
                "男生目标": "降压",
                "推荐策略": "主动降压",
                "风险类型": [],
                "回复强度": "安全",
            },
        },
        {},
        [],
        "女生/对方最后一句：我觉得我们是不是太快了",
    )

    assert answer["labels"]["关系推进目标"] == "暧昧升温"
    assert answer["labels"]["女生状态"] == "正常"
    assert answer["labels"]["男生目标"] == "升温"
    assert answer["labels"]["推荐策略"] == "情绪升温"
    assert answer["labels"]["回复强度"] == "调侃"


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
