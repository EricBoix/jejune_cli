"""configuration_entry: one env var with hint and source file."""

import os
from collections.abc import Callable
from pathlib import Path

_PLACEHOLDER = "CHANGE_ME"


class configuration_entry:

    def __init__(
            self,
            env_var: str,
            hint: str | None = None,
            source_file: str | None = None,
            max_severity: str = "error",
            env_var_validator: Callable[[str], tuple[str, str]] | None = None,
        ) -> None:
        self.env_var = env_var
        self.hint = hint
        self.source_file = source_file
        self.max_severity = max_severity
        self.env_var_validator = env_var_validator

    def load(self, base_dir: Path) -> None:
        """Parse source_file into os.environ (never overrides existing vars)."""
        if not self.source_file:
            return
        path = base_dir / self.source_file
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

    def check(self) -> tuple[str, str]:
        """Return (status, msg) for this single var."""
        val = os.environ.get(self.env_var)
        if val is None:
            return self.max_severity, "missing"
        if _PLACEHOLDER in val:
            return "warn", "placeholder"
        if self.env_var_validator:
            return self.env_var_validator(val)
        return "ok", ""
