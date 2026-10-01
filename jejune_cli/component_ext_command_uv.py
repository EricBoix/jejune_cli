"""uv-command component."""

from .component_ext_command import ExtCommand


class CompCommandUv(ExtCommand):
    def __init__(self) -> None:
        super().__init__(
            name="uv-command",
            command=["uv", "--version"],
            hint="install uv (https://docs.astral.sh/uv/getting-started/installation/)",
        )
