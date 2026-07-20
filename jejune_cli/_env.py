"""Environment loading with precedence: existing env vars > .jejune/env-secrets > .jejune/env-config."""

import os
from pathlib import Path

# Variables forwarded to the jejuneness:extract_knowledge_graph Docker
# container.
EXTRACT_ENV_VARS = [
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "LLM_MODEL_URL",
    "LLM_API_KEY",
    "LLM_MODEL_NAME",
    "TRACELOOP_BASE_URL",  # optional — omitted from Docker args if unset
]

# Variables forwarded to the jj_neo4j_to_rdf_ttl Docker container.
TTL_ENV_VARS = [
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
]

_DOT_JEJUNE = ".jejune"


def dot_jejune(cwd: Path | None = None) -> Path:
    """Return the .jejune/ directory path relative to cwd (defaults to Path.cwd())."""
    return (cwd or Path.cwd()) / _DOT_JEJUNE


def load_env_files(
    config_file: Path | None = None,
    secrets_file: Path | None = None,
) -> None:
    """Load .jejune/env-config then .jejune/env-secrets; existing env vars always take precedence."""
    d = dot_jejune()
    _load(config_file or d / "env-config")
    _load(secrets_file or d / "env-secrets")


def _load(path: Path) -> None:
    """Parse a KEY=VALUE file; skip if absent; never override existing env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in os.environ:
            os.environ[key] = value.strip()


def docker_env_args(var_names: list[str]) -> list[str]:
    """Return [--env KEY=VALUE, ...] Docker args for env vars present in os.environ."""
    args: list[str] = []
    for key in var_names:
        val = os.environ.get(key)
        if val is not None:
            args += ["--env", f"{key}={val}"]
    return args
