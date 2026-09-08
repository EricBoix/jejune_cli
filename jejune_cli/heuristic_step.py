"""HeuristicStep dataclass for next-step guidance."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class HeuristicCondition(Protocol):
    def __call__(self) -> bool: ...


class ComponentCondition:
    """HeuristicCondition that checks a component and its transitive deps are available."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.__name__ = f"{name.replace('-', '_')}_available"

    def __call__(self) -> bool:
        from .component_registry import REGISTRY
        inst = REGISTRY.get(self._name)
        return inst is not None and inst.is_deeply_available()


@dataclass
class HeuristicStep:
    label: str
    command: str | None | Callable[[], str | None]
    order: int = 0
    conditions: list[HeuristicCondition] = field(default_factory=list)
    anti_conditions: list[HeuristicCondition] = field(default_factory=list)
    roles: frozenset[str | None] = field(default_factory=frozenset)

    def resolved_command(self) -> str | None:
        return self.command() if callable(self.command) else self.command
