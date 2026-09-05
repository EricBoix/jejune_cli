"""Deployer extensions component."""
from .component_ext import ext_comp


class comp_extensions(ext_comp):
    def __init__(self) -> None:
        super().__init__(
            name="extensions",
            dependencies=[type(self).registry.get("git-server"), type(self).registry.get("uv-command")],
            hint="run `jejune extensions install`",
        )
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        from .extensions_registry import _extensions_installed
        ok = _extensions_installed()
        return ("ok", "") if ok else ("error", "not installed")


comp_extensions()
