"""Abstract base class for internally-managed (jejune-managed) components."""
from __future__ import annotations

from .component_base import base_comp
from .configuration import configuration as _configuration


class component(base_comp):
    """Abstract internally-managed component.

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
    ) -> None:
        super().__init__(
            name=name,
            dependencies=dependencies,
            optional_dependencies=optional_dependencies,
            hint=hint,
        )
        self.configuration = configuration if configuration is not None else _configuration()

    def check_config(self) -> tuple[str, str] | None:
        """Return (status, message) for a component-specific config check, or None."""
        return None
