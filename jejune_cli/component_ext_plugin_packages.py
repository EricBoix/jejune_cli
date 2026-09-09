"""Plugin-packages component — tracks whether role plugin packages are installed."""
from .component_ext import ext_comp
from .component_registry import ComponentRegistry


class comp_plugin_packages(ext_comp):
    def __init__(self) -> None:
        super().__init__(
            name="plugin-packages",
            dependencies=[ComponentRegistry().get("git-server"), ComponentRegistry().get("uv-command")],
            hint="run `jejune plugin-packages install`",
        )

    def check(self) -> tuple[str, str]:
        from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
        ok = PLUGIN_PACKAGE_CATALOG.packages_installed()
        return ("ok", "") if ok else ("error", "not installed")


