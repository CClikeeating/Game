from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(path: str | Path, root: Path = PROJECT_ROOT) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def read_text(path: str | Path) -> str:
    return resolve_path(path).read_text(encoding="utf-8-sig")


def read_json(path: str | Path) -> Any:
    return json.loads(read_text(path))


def write_json(path: str | Path, data: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    target.write_text(content + ("\n" if content else ""), encoding="utf-8")


def load_config(config_root: str | Path, name: str) -> dict[str, Any]:
    data = load_data(resolve_path(config_root) / name)
    return data if isinstance(data, dict) else {}


def load_data(path: str | Path) -> Any:
    target = resolve_path(path)
    text = target.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if target.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError:
            return parse_simple_yaml(text)
        loaded = yaml.safe_load(text)
        return loaded if loaded is not None else {}

    raise ValueError(f"Unsupported config format or invalid JSON: {target}")


def parse_simple_yaml(text: str) -> Any:
    lines = [
        (len(line) - len(line.lstrip(" ")), line.strip())
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return {}
    value, index = parse_yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError("Unsupported YAML structure")
    return value


def parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    is_list = lines[index][1].startswith("- ")
    if is_list:
        items = []
        while index < len(lines):
            line_indent, stripped = lines[index]
            if line_indent != indent or not stripped.startswith("- "):
                break
            items.append(parse_scalar(stripped[2:].strip()))
            index += 1
        return items, index

    data: dict[str, Any] = {}
    while index < len(lines):
        line_indent, stripped = lines[index]
        if line_indent != indent or stripped.startswith("- "):
            break
        key, sep, value = stripped.partition(":")
        if not sep:
            raise ValueError(f"Unsupported YAML line: {stripped}")
        key = key.strip()
        value = value.strip()
        index += 1
        if value:
            data[key] = parse_scalar(value)
        elif index < len(lines) and lines[index][0] > indent:
            data[key], index = parse_yaml_block(lines, index, lines[index][0])
        else:
            data[key] = {}
    return data, index


def parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def ensure_overwrite_allowed(path: str | Path, overwrite: bool) -> Path:
    target = resolve_path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists. Pass overwrite=True or --overwrite to replace it.")
    return target
