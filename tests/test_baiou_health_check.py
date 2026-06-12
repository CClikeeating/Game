from pathlib import Path

from baiou import health_check


def test_health_check_counts_current_knowledge(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "baiou"
    current = root / "cases" / "knowledge" / "current"
    (current / "local_index").mkdir(parents=True)
    (current / "rag_knowledge_base" / "segments" / "batch_a").mkdir(parents=True)
    (current / "segments.jsonl").write_text('{"segment_id":"a"}\n', encoding="utf-8")
    (current / "local_index" / "segments_index.jsonl").write_text('{"segment_id":"a"}\n', encoding="utf-8")
    (current / "rag_knowledge_base" / "segments" / "batch_a" / "a.md").write_text("# a\n", encoding="utf-8")

    monkeypatch.setattr(health_check, "baiou_output_root", lambda: root)
    monkeypatch.setattr(health_check, "git_info", lambda: {"branch": "main", "commit": "abc", "dirty": False})
    monkeypatch.setattr(health_check, "vector_store_ids", lambda: ["n7s0ou2dpt"])

    report = health_check.collect_health()

    assert report["knowledge"]["segment_count"] == 1
    assert report["knowledge"]["local_index_count"] == 1
    assert report["knowledge"]["rag_markdown_count"] == 1
    assert report["knowledge"]["counts_match"] is True
    assert report["product"]["vector_store_ids"] == ["n7s0ou2dpt"]
