"""uv-command component."""
from .component_ext_command import ext_command
from .component_registry import REGISTRY


class comp_command_uv(ext_command):
    def __init__(self) -> None:
        super().__init__(
            name="uv-command",
            command=["uv", "--version"],
            hint="install uv (https://docs.astral.sh/uv/getting-started/installation/)",
        )


REGISTRY.add(comp_command_uv())
