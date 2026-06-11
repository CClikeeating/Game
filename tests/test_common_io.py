from pathlib import Path

import pytest

from workflow.common import io
from workflow.source_to_chat_turns01 import source_preparation


def test_project_root_is_not_current_working_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    assert io.PROJECT_ROOT.name == "白鸥"
    assert io.resolve_path("workflow").is_dir()


def test_load_config_accepts_yaml_syntax(tmp_path: Path) -> None:
    config_path = tmp_path / "sample.yaml"
    config_path.write_text(
        """
name: demo
enabled: true
count: 3
items:
  - one
  - two
nested:
  value: ok
""".strip(),
        encoding="utf-8",
    )

    assert io.load_data(config_path) == {
        "name": "demo",
        "enabled": True,
        "count": 3,
        "items": ["one", "two"],
        "nested": {"value": "ok"},
    }


def test_prepare_requires_overwrite_for_existing_output(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    existing = runs_root / "case_001"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("old", encoding="utf-8")

    monkeypatch.setattr(source_preparation, "RUNS_ROOT", runs_root)

    with pytest.raises(FileExistsError):
        source_preparation.prepare("image", tmp_path / "input.png", run_id="case_001")

    assert (existing / "keep.txt").exists()
