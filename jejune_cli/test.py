import subprocess
from pathlib import Path

import click
import yaml

from ._env import dot_jejune

_TMP_PATTERN = ".jejune/tmp/"
_SCHEMA_PATH = Path(__file__).parent / "schema" / "doc.yaml"


def _load_doc_schema() -> dict:
    return yaml.safe_load(_SCHEMA_PATH.read_text())


def _ensure_gitignored() -> None:
    gitignore = dot_jejune().parent / ".gitignore"
    if gitignore.exists():
        if any(l.strip() == _TMP_PATTERN for l in gitignore.read_text().splitlines()):
            return
        with gitignore.open("a") as f:
            f.write(f"{_TMP_PATTERN}\n")
    else:
        gitignore.write_text(f"{_TMP_PATTERN}\n")


def _tmp_dir() -> Path:
    tmp = dot_jejune() / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    _ensure_gitignored()
    return tmp


def _check_doc_yaml(
    repo_dir: Path,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (errors, file_refs).

    file_refs: (key, rel_path) for every file_field present in doc.yaml.
    errors: non-empty when doc.yaml is missing or a referenced file is absent.
    """
    doc_yaml = repo_dir / "doc.yaml"
    if not doc_yaml.exists():
        return [f"doc.yaml missing (see {_SCHEMA_PATH} for the expected format)"], []

    schema = _load_doc_schema()
    data = yaml.safe_load(doc_yaml.read_text()) or {}
    errors: list[str] = []
    file_refs: list[tuple[str, str]] = []

    for field in schema.get("required_fields", {}):
        if field not in data:
            errors.append(f"required field {field!r} missing")

    for key in schema.get("file_fields", []):
        rel = data.get(key)
        if rel is None:
            continue
        file_refs.append((key, rel))
        if not (repo_dir / rel).exists():
            errors.append(f"{key}: {rel!r} not found")

    if errors:
        errors.append(f"see {_SCHEMA_PATH} for the expected format")
    return errors, file_refs


