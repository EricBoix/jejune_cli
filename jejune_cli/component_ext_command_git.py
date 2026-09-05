"""git-command component."""
from .component_ext_command import ext_command
from .component_base import base_comp
COMP_REGISTRY = base_comp.registry


class comp_command_git(ext_command):
    def __init__(self) -> None:
        super().__init__(
            name="git-command",
            command=["git", "--version"],
            hint="install git (https://git-scm.com)",
        )
        self.visible = lambda: COMP_REGISTRY.get("ecosystem").ecosystem_needs_remote()
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        if not COMP_REGISTRY.get("ecosystem").ecosystem_needs_remote():
            return "ok", ""
        return super().check()


comp_command_git()
