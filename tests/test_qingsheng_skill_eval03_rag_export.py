from pathlib import Path

from workflow.qingsheng_skill_eval03.build_assets import build_rag_knowledge_base
from workflow.qingsheng_skill_eval03.io_utils import read_json


def test_build_rag_knowledge_base_exports_markdown_and_manifests(tmp_path: Path) -> None:
    rows = [
        {
            "case_id": "case_001",
            "stage_number": 4,
            "stage_label": "阶段4 暧昧拉扯",
            "stage_structure": {
                "primary_stage": {"stage_number": 4, "stage_label": "阶段4 暧昧拉扯", "confidence": 0.82},
                "stage_path": [
                    {"stage_number": 3, "stage_label": "阶段3 关系升温", "evidence_turn_ids": ["turn_0008"]},
                    {"stage_number": 4, "stage_label": "阶段4 暧昧拉扯", "evidence_turn_ids": ["turn_0012"]},
                    {"stage_number": 6, "stage_label": "阶段6 亲密升级", "evidence_turn_ids": ["turn_0018"], "is_cross_stage": True},
                ],
                "key_stage_nodes": [
                    {
                        "turn_id": "turn_0012",
                        "stage_number": 4,
                        "stage_label": "阶段4 暧昧拉扯",
                        "quote": "那你想当什么角色",
                        "why": "女生打开暧昧推进窗口",
                    }
                ],
            },
            "outcome": "女生持续接话，关系升温",
            "relationship_arc": "从普通聊天进入明显调情",
            "female_state": "愿意配合玩梗",
            "male_goal": "保持框架并推进暧昧",
            "signals": [
                {
                    "type": "IOI",
                    "quote": "那你想当什么角色",
                    "interpretation": "女生给男生继续发挥的空间",
                }
            ],
            "good_replies": [
                {
                    "quote": "我们之间没有别人",
                    "why_good": "没有解释，直接把暧昧关系框住",
                    "transferable_rule": "女生抛身份/角色梗时，优先把关系框回两人之间。",
                }
            ],
            "bad_replies": [
                {
                    "quote": "哈哈我不知道",
                    "why_bad": "回避了女生抛出的暧昧窗口",
                    "better_reply": "我们之间没有别人",
                }
            ],
            "gold_reference": {
                "next_reply": "我们之间没有别人",
                "why": "短句、有框架、接住调情窗口。",
            },
            "search_text": "暧昧拉扯\n我们之间没有别人",
        }
    ]

    summary = build_rag_knowledge_base(tmp_path, "batch_test", rows)

    case_doc = tmp_path / "rag_knowledge_base" / "cases" / "case_001.md"
    assert case_doc.exists()
    content = case_doc.read_text(encoding="utf-8")
    assert "# 案例：case_001" in content
    assert "关系阶段：阶段4 暧昧拉扯" in content
    assert "## 阶段路径" in content
    assert "阶段3 关系升温" in content
    assert "turn_0012" in content
    assert "## 男方好回复" in content
    assert "我们之间没有别人" in content
    assert "## 可迁移规则" in content
    assert '{"type":' not in content

    index_path = tmp_path / "rag_knowledge_base" / "qingsheng_cases_index.jsonl"
    assert index_path.exists()
    assert '"case_id": "case_001"' in index_path.read_text(encoding="utf-8")

    manifest_path = tmp_path / "rag_knowledge_base" / "upload_manifest.csv"
    assert manifest_path.exists()
    manifest = manifest_path.read_text(encoding="utf-8-sig")
    assert "case_id,file_path,stage_label" in manifest
    assert "case_001" in manifest

    build_summary = read_json(tmp_path / "rag_knowledge_base" / "rag_build_summary.json")
    assert build_summary["batch_id"] == "batch_test"
    assert build_summary["document_count"] == 1
    assert summary["document_count"] == 1
