"""Abstract base class for all jejune components."""

from abc import ABC, abstractmethod
from typing import Callable, ClassVar


class BaseComp(ABC):
    mandatory: ClassVar[bool] = True

    def __init__(
        self,
        name: str,
        dependencies: "list[BaseComp] | None" = None,
        optional_dependencies: "list[BaseComp] | None" = None,
        hint: str | None = None,
        use_hint: str | None = None,
        plugin_deps: list[str] | None = None,
        install_plugin_deps: list[str] | None = None,
    ) -> None:
        self.name = name
        self.cli_name: str | None = None
        self.dependencies: list[BaseComp] = dependencies or []
        self.optional_dependencies: list[BaseComp] = optional_dependencies or []
        self.conditional_dependencies: list[tuple[Callable[[], bool], BaseComp]] = []
        self.hint = hint
        self.use_hint = use_hint
        self.plugin_deps: list[str] = plugin_deps or []
        self.install_plugin_deps: list[str] = install_plugin_deps or []
        self.runtime_dependencies: "dict[str, BaseComp]" = {}

    def set_hint(self, hint: str) -> None:
        self.hint = hint

    def set_mandatory(self, value: bool) -> None:
        self.mandatory = value  # type: ignore[misc]

    def set_runtime_dependency(self, name: str, dep: "BaseComp") -> None:
        """Register a dep used at runtime in check(); excluded from topology and activation."""
        self.runtime_dependencies[name] = dep

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
        return (
            all(dep.is_deeply_available(_seen) for dep in self.active_deps())
            and self.is_available()
        )

    def ordering_deps(self) -> "list[BaseComp]":
        """Required + conditional deps; used for topological ordering (optional excluded)."""
        return self.dependencies + [d for _, d in self.conditional_dependencies]

    def all_deps(self) -> "list[BaseComp]":
        """Required + optional + conditional; used for registry validation."""
        return (
            self.dependencies
            + self.optional_dependencies
            + [d for _, d in self.conditional_dependencies]
        )

    def active_deps(self) -> "list[BaseComp]":
        """Required + active conditional deps; used for runtime checks."""
        return self.dependencies + [d for c, d in self.conditional_dependencies if c()]
