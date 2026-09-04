"""Configuration of a component: some components required to be configured with a file (or set of files) or possibly environment variables that are known and used by jejune to configure each specific component."""

import os
from collections.abc import Callable

_PLACEHOLDER = "CHANGE_ME"


class configuration:

    def __init__(
            self,
            hint: str | None = None,
            env_vars: list[str] | None = None,
            max_severity: str = "error",
            env_var_validator: Callable[[str], tuple[str, str]] | None = None,
        ) -> None:
        self.hint = hint
        self.env_vars = env_vars or []
        self.max_severity = max_severity
        self.env_var_validator = env_var_validator

    def check_vars(self) -> list[tuple[str, str]]:
        """Return [(key, state)] for each env_var.

        state is "ok", "missing", or "placeholder".
        """
        result = []
        for key in self.env_vars:
            val = os.environ.get(key)
            if val is None:
                result.append((key, "missing"))
            elif _PLACEHOLDER in val:
                result.append((key, "placeholder"))
            else:
                result.append((key, "ok"))
        return result

    def check(self) -> tuple[str, str, str]:
        """Return (status, msg, hint).

        status: "ok" | "warn" | "error"
        msg:    raw diagnostic (which vars are missing/wrong)
        hint:   human-readable remediation stored on this instance
        """
        if not self.env_vars:
            return "ok", "", ""

        states = self.check_vars()

        if all(s == "ok" for _, s in states):
            status, msg = "ok", ""
        elif all(s in ("missing", "placeholder") for _, s in states):
            status, msg = "warn", "not configured"
        else:
            issues = [f"{k}: {s}" for k, s in states if s != "ok"]
            status, msg = "error", "; ".join(issues)

        if self.max_severity == "warn" and status == "error":
            status = "warn"
        if status == "ok" and self.env_var_validator is not None:
            val = os.environ.get(self.env_vars[0], "")
            status, msg = self.env_var_validator(val)

        return status, msg, self.hint or ""
