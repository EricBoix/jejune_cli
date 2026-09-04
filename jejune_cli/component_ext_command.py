"""Base class for command-based external components."""
import subprocess

from .component_ext import ext_comp


class ext_command(ext_comp):
    """External CLI tool checked via subprocess."""

    def __init__(
        self,
        name: str,
        command: list[str],
        dependencies: list[str] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(name=name, dependencies=dependencies, hint=hint)
        self.command = command

    def check(self) -> tuple[str, str]:
        try:
            subprocess.run(self.command, capture_output=True, check=True)
            return "ok", ""
        except Exception:
            return "error", f"{self.command[0]} not found on PATH"
