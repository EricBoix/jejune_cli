"""git-command component."""
from .component_ext_command import ext_command


class comp_command_git(ext_command):
    _ecosystem = None

    def __init__(self) -> None:
        super().__init__(
            name="git-command",
            command=["git", "--version"],
            hint="install git (https://git-scm.com)",
        )

    def check(self) -> tuple[str, str]:
        if comp_command_git._ecosystem is None or not comp_command_git._ecosystem.ecosystem_needs_remote():
            return "ok", ""
        return super().check()
