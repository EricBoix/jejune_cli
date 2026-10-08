"""Base class for components with configuration (internal or external)."""

from __future__ import annotations

from .component_base import BaseComp
from .configuration import Configuration


class ConfComp(BaseComp):
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
        configuration: Configuration | None = None,
        plugin_deps: list[str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            dependencies=dependencies,
            optional_dependencies=optional_dependencies,
            hint=hint,
            plugin_deps=plugin_deps,
        )
        self.configuration: Configuration = (
            configuration if configuration is not None else Configuration()
        )

    def set_configuration(self, cfg: Configuration) -> None:
        self.configuration = cfg

    def check_config(self) -> tuple[str, str]:
        """Return (status, msg) for the configuration check.

        Default delegates to self.configuration.check(). Override this in
        subclasses whose configuration is not expressed as env-var entries.
        """
        status, msg, _ = self.configuration.check()
        return status, msg
