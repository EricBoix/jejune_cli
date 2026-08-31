import subprocess
from pathlib import Path

import click
import yaml

from ._env import dot_jejune

_TMP_PATTERN = ".jejune/tmp/"
_SCHEMA_PATH = Path(__file__).parent / "schema" / "manifest.yaml"


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

    file_refs: (key, rel_path) for every file_field present in manifest.yaml.
    errors: non-empty when manifest.yaml is missing or a referenced file is absent.
    """
    doc_yaml = repo_dir / "manifest.yaml"
    if not doc_yaml.exists():
        return [f"manifest.yaml missing (see {_SCHEMA_PATH} for the expected format)"], []

    schema = _load_doc_schema()
    data = yaml.safe_load(doc_yaml.read_text()) or {}
    errors: list[str] = []
    file_refs: list[tuple[str, str]] = []

    for field in schema.get("required_fields", {}):
        if field not in data:
            errors.append(f"required field {field!r} missing")

    for key in schema.get("required_file_fields", []):
        rel = data.get(key)
        if rel is None:
            errors.append(f"required field {key!r} missing")
        elif not (repo_dir / rel).exists():
            file_refs.append((key, rel))
            errors.append(f"{key}: {rel!r} not found")
        else:
            file_refs.append((key, rel))

    for key in schema.get("file_fields", []):
        if key in schema.get("required_file_fields", []):
            continue
        rel = data.get(key)
        if rel is None:
            continue
        file_refs.append((key, rel))
        if not (repo_dir / rel).exists():
            errors.append(f"{key}: {rel!r} not found")

    known_keys = (
        set(schema.get("required_fields", {}).keys())
        | set(schema.get("optional_fields", {}).keys())
        | set(schema.get("file_fields", []))
    )
    for key in data:
        if key not in known_keys:
            errors.append(f"unknown field {key!r}")

    if errors:
        errors.append(f"see {_SCHEMA_PATH} for the expected format")
    return errors, file_refs


def _manifest_config_status(repo_dir: Path) -> tuple[str, str]:
    """(status, msg) for the Config column in jejune doctor.

    "error" when required fields are absent, "warn" for unknown fields only.
    """
    doc_yaml = repo_dir / "manifest.yaml"
    if not doc_yaml.exists():
        return "error", "manifest.yaml missing"
    schema = _load_doc_schema()
    data = yaml.safe_load(doc_yaml.read_text()) or {}
    missing = [f for f in schema.get("required_fields", {}) if f not in data]
    missing += [f for f in schema.get("required_file_fields", []) if f not in data]
    if missing:
        return "error", f"required field(s) missing: {', '.join(missing)}"
    known_keys = (
        set(schema.get("required_fields", {}).keys())
        | set(schema.get("optional_fields", {}).keys())
        | set(schema.get("file_fields", []))
    )
    unknown = [k for k in data if k not in known_keys]
    if unknown:
        return "warn", f"unknown field(s): {', '.join(unknown)}"
    return "ok", ""


def _manifest_avail_status(repo_dir: Path) -> tuple[str, str]:
    """(status, msg) for the Avail column in jejune doctor.

    Checks only that file-field values point to existing files.
    """
    doc_yaml = repo_dir / "manifest.yaml"
    if not doc_yaml.exists():
        return "warn", "manifest.yaml missing"
    schema = _load_doc_schema()
    data = yaml.safe_load(doc_yaml.read_text()) or {}
    missing_files = [
        f"{key}: {rel!r} not found"
        for key in schema.get("file_fields", [])
        if (rel := data.get(key)) and not (repo_dir / rel).exists()
    ]
    if missing_files:
        return "warn", f"{len(missing_files)} file(s) not found"
    return "ok", ""


