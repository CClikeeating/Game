from pathlib import Path


def test_baiou_python_code_does_not_import_legacy_modules() -> None:
    root = Path(__file__).resolve().parents[1] / "baiou"
    forbidden = [
        "workflow.",
        "workV.",
        "qingsheng_skill_runtime04",
        "qingsheng_skill_web05",
        "qingsheng_cases02",
        "qingsheng_skill_eval03",
    ]

    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path.relative_to(root)}: {token}")

    assert offenders == []
