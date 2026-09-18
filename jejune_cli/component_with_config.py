"""Base class for components with configuration (internal or external)."""
from __future__ import annotations

from .component_base import base_comp
from .configuration import configuration as _configuration


class conf_comp(base_comp):
    """Component with configuration.

    Subclasses must implement check(). The configuration attribute holds a
    configuration instance whose entries describe required env vars.
    Subclasses with non-env-var configuration (e.g. YAML schema validation)
    should override check_config() to return the appropriate status.
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
        self.configuration: _configuration = configuration if configuration is not None else _configuration()

    def check_config(self) -> tuple[str, str]:
        """Return (status, msg) for the configuration check.

        Default delegates to self.configuration.check(). Override this in
        subclasses whose configuration is not expressed as env-var entries.
        """
        status, msg, _ = self.configuration.check()
        return status, msg
