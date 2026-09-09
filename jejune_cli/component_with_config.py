"""Base class for components with configuration (internal or external)."""
from __future__ import annotations

from .component_base import base_comp
from .configuration import configuration as _configuration


class conf_comp(base_comp):
    """Component with configuration.

    Subclasses must implement check(). check_config() may be overridden for
    components whose availability depends on a configuration file check.
    """

    def __init__(
        self,
        name: str,
        dependencies: list[str] | None = None,
        optional_dependencies: list[str] | None = None,
        hint: str | None = None,
        configuration: _configuration | None = None,
        plugin_deps: list[str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            dependencies=dependencies,
            optional_dependencies=optional_dependencies,
            hint=hint,
            plugin_deps=plugin_deps,
        )
        self.configuration = configuration if configuration is not None else _configuration()

    def check_config(self) -> tuple[str, str] | None:
        """Return (status, message) for a component-specific config check, or None."""
        return None
