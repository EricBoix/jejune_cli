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
        self.visible = lambda: REGISTRY.get("ecosystem").ecosystem_needs_remote()
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        if not REGISTRY.get("ecosystem").ecosystem_needs_remote():
            return "ok", ""
        return super().check()


comp_command_git()
