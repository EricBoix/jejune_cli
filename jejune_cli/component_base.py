"""Abstract base class for all jejune components."""
from abc import ABC, abstractmethod
from typing import Callable, ClassVar


class base_comp(ABC):
    mandatory: ClassVar[bool] = True

    def __init__(
        self,
        name: str,
        dependencies: "list[base_comp] | None" = None,
        optional_dependencies: "list[base_comp] | None" = None,
        hint: str | None = None,
    ) -> None:
        self.name = name
        self.dependencies: list[base_comp] = dependencies or []
        self.optional_dependencies: list[base_comp] = optional_dependencies or []
        self.conditional_dependencies: list[tuple[Callable[[], bool], base_comp]] = []
        self.hint = hint

    @abstractmethod
    def check(self) -> tuple[str, str]:
        """Return (status, message) where status is 'ok', 'warn', or 'error'."""
        ...

    def is_available(self) -> bool:
        """Return True when check() reports ok or warn (non-error)."""
        return self.check()[0] != "error"

    def is_deeply_available(self, _seen: set[str] | None = None) -> bool:
        """Return True if this component and all transitive active deps are available."""
        if _seen is None:
            _seen = set()
        if self.name in _seen:
            return True
        _seen.add(self.name)
        return all(dep.is_deeply_available(_seen) for dep in self.active_deps()) and self.is_available()

    def ordering_deps(self) -> "list[base_comp]":
        """Required + conditional deps; used for topological ordering (optional excluded)."""
        return self.dependencies + [d for _, d in self.conditional_dependencies]

    def all_deps(self) -> "list[base_comp]":
        """Required + optional + conditional; used for registry validation."""
        return self.dependencies + self.optional_dependencies + [d for _, d in self.conditional_dependencies]

    def active_deps(self) -> "list[base_comp]":
        """Required + active conditional deps; used for runtime checks."""
        return self.dependencies + [d for c, d in self.conditional_dependencies if c()]

