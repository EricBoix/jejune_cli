"""Plugin-packages component — tracks whether role plugin packages are installed."""

from .component_ext import ExtComp


class comp_plugin_packages(ExtComp):
    def __init__(self, git_server, uv_command, catalog) -> None:
        super().__init__(
            name="plugin-packages",
            dependencies=[git_server, uv_command],
            hint="run `jejune plugin-packages install`",
        )
        self._catalog = catalog

    def check(self) -> tuple[str, str]:
        ok = self._catalog.packages_installed()
        return ("ok", "") if ok else ("error", "not installed")

    def packages_installed(self, role: "str | None" = None) -> bool:
        return self._catalog.packages_installed(role)

    def install_packages(
        self, role: "str | None" = None, no_cache: bool = False
    ) -> None:
        self._catalog.install_packages(role, no_cache=no_cache)

    def expected_plugin_names(self, role: "str | None" = None) -> list[str]:
        return self._catalog.expected_plugin_names(role)

    def repo_name_for(self, component_name: str) -> "str | None":
        return self._catalog.repo_name_for(component_name)
