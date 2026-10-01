"""git-command component."""

from .component_ext_command import ExtCommand


class CompCommandGit(ExtCommand):
    def __init__(self) -> None:
        super().__init__(
            name="git-command",
            command=["git", "--version"],
            hint="install git (https://git-scm.com)",
        )

    def check(self) -> tuple[str, str]:
        ecosystem = self.runtime_dependencies.get("ecosystem")
        if ecosystem is None or not ecosystem.ecosystem_needs_remote():
            return "ok", ""
        return super().check()
