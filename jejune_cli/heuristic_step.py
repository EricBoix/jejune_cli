"""HeuristicStep dataclass for next-step guidance."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class HeuristicStep:
    label: str
    command: str | None | Callable[[], str | None]
    order: int = 0
    conditions: list[Callable[[], bool]] = field(default_factory=list)
    anti_conditions: list[Callable[[], bool]] = field(default_factory=list)
    roles: frozenset[str | None] = field(default_factory=frozenset)

    def resolved_command(self) -> str | None:
        return self.command() if callable(self.command) else self.command
