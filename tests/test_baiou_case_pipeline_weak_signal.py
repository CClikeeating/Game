from pathlib import Path

from openpyxl import Workbook

from baiou.case_pipeline.production.build_segments import ensure_weak_signal_missing_nodes
from baiou.case_pipeline.production.materialize_missing_nodes import materialize_missing_nodes
from baiou.case_pipeline.production import audit_weak_signal_coverage as audit
from baiou.common.io import read_json, read_text, write_json


def test_case_pipeline_prompts_cover_weak_acknowledgement_rules() -> None:
    case_prompt = read_text("baiou/prompts/case_segment_v01.md")
    review_prompt = read_text("baiou/prompts/segment_review_v01.md")
    models = read_json("baiou/config/case_pipeline/models.json")

    assert "普通案例目标 8-14 个片段，最多 16 个" in case_prompt
    assert "长案例或高信息密度案例目标 10-16 个片段，最多 20 个" in case_prompt
    assert "弱承接不是流水账" in case_prompt
    assert "弱承接硬性覆盖" in case_prompt
    assert "`source_turn_ids` 必须包含女生弱承接那一轮" in case_prompt
    assert "输出前做弱承接覆盖自检" in case_prompt
    assert "优先体现边界价值" in case_prompt
    assert "不要把“弱承接后强行叫老婆/性张力拉升/亲密推进”当作默认弱承接样本" in case_prompt
    assert "高价值片段不等于高热度片段" in case_prompt
    assert "动作价值" in case_prompt
    assert "边界价值" in case_prompt
    assert "校准价值" in case_prompt
    assert "`高意向推进期` 需要更强上下文证据" in case_prompt
    assert "`关系推进目标=亲密升级推进/性关系推进` 需要女生明确承接" in case_prompt
    assert "`女生状态=防御/低投入` 需要明显抗拒" in case_prompt
    assert "女生测试、自嘲、求安慰、轻微质疑、正常拉扯" in case_prompt
    assert "证据不足时弱收紧主标签" in case_prompt
    assert "不要强行解读为暧昧、口是心非、怕男生担心" in case_prompt
    assert "先做弱承接覆盖审计，再看其他漏拆" in review_prompt
    assert "弱承接漏拆检查" in review_prompt
    assert "补拆项的 `source_turn_ids` 必须包含女生弱承接那一轮" in review_prompt
    assert "主模型 0 覆盖" in review_prompt
    assert "弱承接补拆的优先目标是边界校准" in review_prompt
    assert "弱信号过度升温检查" in review_prompt
    assert models["case_primary"]["max_tokens"] == 26000
    assert models["case_review"]["max_tokens"] == 16000


def test_weak_signal_audit_reports_primary_and_final_coverage(tmp_path: Path) -> None:
    source_root = tmp_path / "source" / "batch_a"
    write_json(
        source_root / "batch_chat_turns.json",
        {
            "cases": [
                {
                    "case_id": "case_001",
                    "blocks": [
                        {
                            "turns": [
                                {"turn_id": "turn_001", "speaker": "male", "text": "少喝点 早点回去"},
                                {"turn_id": "turn_002", "speaker": "female", "text": "嗯嗯"},
                                {"turn_id": "turn_003", "speaker": "male", "text": "到家说一声"},
                            ]
                        }
                    ],
                }
            ]
        },
    )
    batch_root = tmp_path / "segments" / "batch_new"
    case_root = batch_root / "cases" / "case_001"
    write_json(
        batch_root / "segments_manifest.json",
        {"cases": [{"case_id": "case_001", "case_dir": str(case_root)}]},
    )
    write_json(
        case_root / "primary_result.json",
        {"parsed": {"segments": [{"segment_id": "seg_primary", "source_turn_ids": ["turn_001"]}]}},
    )
    write_json(
        case_root / "segments.json",
        {
            "segments": [
                {
                    "segment_id": "seg_final",
                    "source_turn_ids": ["turn_001", "turn_002", "turn_003"],
                    "聊天阶段": "熟悉期",
                    "关系推进目标": "无",
                    "女生状态": "正常",
                    "男生目标": "接话",
                    "推荐策略": "共情回应",
                    "回复强度": "安全",
                    "高热度信号": "无",
                }
            ]
        },
    )
    write_json(
        case_root / "review_result.json",
        {
            "parsed": {
                "segment_reviews": [
                    {
                        "segment_id": "seg_final",
                        "verdict": "revise",
                        "issues": [
                            {
                                "field": "聊天阶段",
                                "current_value": "暧昧升温期",
                                "suggested_value": "熟悉期",
                                "reason": "弱承接证据不足。",
                            },
                            {
                                "field": "次要标签.说明",
                                "suggested_value": "边界说明",
                                "reason": "补充辅助判断。",
                            },
                        ],
                    }
                ],
                "missing_nodes": [
                    {
                        "source_turn_ids": ["turn_002"],
                        "reason": "弱承接有低压力收住价值",
                        "suggested_segment_focus": "自然收尾",
                    }
                ]
            }
        },
    )

    result = audit.audit_batches(
        source_root,
        ["batch_new"],
        segments_root=tmp_path / "segments",
    )
    batch = result["batches"][0]
    case = batch["cases"][0]

    assert batch["weak_turn_count"] == 1
    assert batch["primary_covered_count"] == 0
    assert batch["final_covered_count"] == 1
    assert batch["weak_missing_turn_count"] == 1
    assert batch["weak_actionable_count"] == 1
    assert batch["weak_missing_node_count"] == 1
    assert batch["review_focus_issue_count"] == 1
    assert batch["review_issue_counts"]["聊天阶段"] == 1
    assert batch["review_issue_counts"]["次要标签"] == 1
    assert batch["review_verdict_counts"]["revise"] == 1
    assert case["weak_turns"][0]["text"] == "嗯嗯"
    assert case["weak_turns"][0]["primary_segments"] == []
    assert case["weak_turns"][0]["final_segments"] == ["seg_final"]
    assert case["weak_turns"][0]["missing_nodes"] == [1]
    assert case["weak_turns"][0]["actionable"]
    assert case["weak_missing_turn_count"] == 1
    assert case["weak_actionable_count"] == 1
    assert case["review_focus_issue_count"] == 1
    assert batch["label_counts"]["推荐策略"]["共情回应"] == 1


def test_weak_signal_audit_does_not_match_ack_inside_long_word() -> None:
    exact = {audit.normalize_text(item) for item in audit.DEFAULT_WEAK_ACKS}

    assert audit.is_weak_ack_text("好的呢", exact, audit.DEFAULT_WEAK_SUBSTRINGS)
    assert audit.is_weak_ack_text("哈哈哈哈哈 行吧 我误会了好吧", exact, audit.DEFAULT_WEAK_SUBSTRINGS)
    assert not audit.is_weak_ack_text("如果我说我是成熟类型，岂不是说我就你喜好的类型", exact, audit.DEFAULT_WEAK_SUBSTRINGS)


def test_build_segments_adds_deterministic_weak_signal_missing_node() -> None:
    case = {
        "case_id": "case_001",
        "blocks": [
            {
                "turns": [
                    {"turn_id": "turn_001", "speaker": "male", "text": "少喝点 早点回去"},
                    {"turn_id": "turn_002", "speaker": "female", "text": "嗯嗯"},
                    {"turn_id": "turn_003", "speaker": "male", "text": "到家说一声"},
                ]
            }
        ],
    }
    primary = {"segments": [{"segment_id": "seg_001", "source_turn_ids": ["turn_001"]}]}

    review = ensure_weak_signal_missing_nodes(case, primary, {"missing_nodes": []})

    assert len(review["missing_nodes"]) == 1
    assert "turn_002" in review["missing_nodes"][0]["source_turn_ids"]
    assert "确定性覆盖检查" in review["missing_nodes"][0]["reason"]

    covered_primary = {"segments": [{"segment_id": "seg_001", "source_turn_ids": ["turn_001", "turn_002"]}]}
    covered_review = ensure_weak_signal_missing_nodes(case, covered_primary, {"missing_nodes": []})

    assert covered_review["missing_nodes"] == []


def test_materialize_missing_nodes_adds_stable_approved_segments(tmp_path: Path) -> None:
    source_root = tmp_path / "source" / "batch_a"
    write_json(
        source_root / "batch_chat_turns.json",
        {
            "cases": [
                {
                    "case_id": "case_001",
                    "blocks": [
                        {
                            "turns": [
                                {"turn_id": "turn_001", "speaker": "male", "text": "少喝点，早点回去"},
                                {"turn_id": "turn_002", "speaker": "female", "text": "嗯嗯"},
                                {"turn_id": "turn_003", "speaker": "male", "text": "到家说一声"},
                            ]
                        }
                    ],
                }
            ]
        },
    )
    batch_root = tmp_path / "segments" / "batch_new"
    case_root = batch_root / "cases" / "case_001"
    write_json(
        batch_root / "segments_manifest.json",
        {
            "source_bundle": str(source_root),
            "cases": [{"case_id": "case_001", "case_dir": str(case_root)}],
        },
    )
    write_json(case_root / "segments.json", {"segments": []})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "missing_nodes_review"
    ws.append(["missing_id", "case_id", "source_turn_ids", "当前上下文", "复核模型漏拆理由", "优先级", "建议补拆重点", "人工结论", "人工备注"])
    ws.append(["missing_0001", "case_001", "turn_001, turn_002, turn_003", "", "弱承接需要边界校准", "medium", "低压力自然收尾，不强行升温", "需要补拆", "PM确认"])
    ws.append(["missing_0002", "case_001", "turn_001", "", "低优先级", "low", "暂缓项", "暂缓", ""])
    review_path = batch_root / "human_review_segments.xlsx"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(review_path)

    result = materialize_missing_nodes("batch_new", segments_root=tmp_path / "segments")
    second = materialize_missing_nodes("batch_new", segments_root=tmp_path / "segments")
    payload = read_json(case_root / "segments.json")
    segment = payload["segments"][0]
    manifest = read_json(batch_root / "segments_manifest.json")

    assert result["created_count"] == 1
    assert second["updated_count"] == 1
    assert len(payload["segments"]) == 1
    assert segment["segment_id"] == "case_001_supp_missing_missing_0001"
    assert segment["quality_status"] == "approved"
    assert segment["need_human_review"] is False
    assert segment["推荐策略"] == "主动降压"
    assert segment["回复强度"] == "安全"
    assert segment["高热度信号"] == "无"
    assert "turn_002" in segment["source_turn_ids"]
    assert manifest["cases"][0]["approved_count"] == 1
