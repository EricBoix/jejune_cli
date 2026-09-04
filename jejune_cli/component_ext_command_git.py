"""git-command component."""
from .component_ext_command import ext_command
from .component_registry import REGISTRY


class comp_command_git(ext_command):
    def __init__(self) -> None:
        super().__init__(
            name="git-command",
            command=["git", "--version"],
            hint="install git (https://git-scm.com)",
        )

    def check(self) -> tuple[str, str]:
        from .ecosystem import ecosystem_needs_remote
        if not ecosystem_needs_remote():
            return "ok", ""
        return super().check()


REGISTRY.add(comp_command_git())
