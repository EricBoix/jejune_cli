"""Deployer extensions component."""
from .component_ext import ext_comp
from .component_registry import REGISTRY


class comp_extensions(ext_comp):
    def __init__(self) -> None:
        super().__init__(
            name="extensions",
            dependencies=["git-repos-access", "uv-command"],
            hint="run `jejune deployment install`",
        )

    def check(self) -> tuple[str, str]:
        from .deployer_extensions import _extensions_installed
        ok = _extensions_installed()
        return ("ok", "") if ok else ("error", "not installed")


REGISTRY.add(comp_extensions())
