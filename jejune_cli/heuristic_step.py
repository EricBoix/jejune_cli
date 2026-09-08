"""HeuristicStep dataclass for next-step guidance."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class HeuristicCondition(Protocol):
    def __call__(self) -> bool: ...


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
