"""Workspace path helper and Docker env-forwarding utility."""

from pathlib import Path

_DOT_JEJUNE = ".jejune"


def dot_jejune(cwd: Path | None = None) -> Path:
    """Return the .jejune/ directory path relative to cwd (defaults to Path.cwd())."""
    return (cwd or Path.cwd()) / _DOT_JEJUNE
