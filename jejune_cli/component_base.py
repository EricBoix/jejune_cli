"""Abstract base class for all jejune components."""
from abc import ABC, abstractmethod


class base_comp(ABC):
    def __init__(
        self,
        name: str,
        dependencies: list[str] | None = None,
        optional_dependencies: list[str] | None = None,
        hint: str | None = None,
    ) -> None:
        self.name = name
        self.dependencies = dependencies or []
        self.optional_dependencies = optional_dependencies or []
        self.hint = hint

    @abstractmethod
    def check(self) -> tuple[str, str]:
        """Return (status, message) where status is 'ok', 'warn', or 'error'."""
        ...

    def is_available(self) -> bool:
        """Return True when check() reports ok or warn (non-error)."""
        return self.check()[0] != "error"
