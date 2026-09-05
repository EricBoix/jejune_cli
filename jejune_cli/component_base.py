"""Abstract base class for all jejune components."""
from abc import ABC, abstractmethod
from typing import Callable, ClassVar

from .component_registry import ComponentRegistry


class base_comp(ABC):
    registry: ClassVar[ComponentRegistry] = ComponentRegistry()

    def __init__(
        self,
        name: str,
        dependencies: "list[base_comp] | None" = None,
        optional_dependencies: "list[base_comp] | None" = None,
        hint: str | None = None,
    ) -> None:
        self.name = name
        self.visible: Callable[[], bool] | None = None
        self.dependencies: list[base_comp] = dependencies or []
        # Optional dependencies depend on the configuration choices
        self.optional_dependencies: list[base_comp] = optional_dependencies or []
        self.hint = hint

    @abstractmethod
    def check(self) -> tuple[str, str]:
        """Return (status, message) where status is 'ok', 'warn', or 'error'."""
        ...

    def is_available(self) -> bool:
        """Return True when check() reports ok or warn (non-error)."""
        return self.check()[0] != "error"
