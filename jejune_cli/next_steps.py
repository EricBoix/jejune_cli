"""Static and heuristic next-step guidance for jejune CLI commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import click


@dataclass
class HeuristicStep:
    label: str
    command: str | None
    order: int
    conditions: list[Callable[[], bool]] = field(default_factory=list)
    anti_conditions: list[Callable[[], bool]] = field(default_factory=list)


_STATIC_REGISTRY: dict[str, list[str]] = {}
_REGISTRY: list[HeuristicStep] = []
_ROLES_WITH_HEURISTICS: set[str] = set()


def register_static(cmd_path: str, hints: list[str]) -> None:
    _STATIC_REGISTRY[cmd_path] = hints


def echo_next_steps(cmd_path: str, hints: list[str] | None = None) -> None:
    steps = hints if hints is not None else _STATIC_REGISTRY.get(cmd_path, [])
    if not steps:
        return
    click.echo()
    click.echo("Next steps:")
    for i, hint in enumerate(steps, 1):
        click.echo(f"  {i}. {hint}")


def register_heuristic(step: HeuristicStep, roles: set[str]) -> None:
    _REGISTRY.append(step)
    _ROLES_WITH_HEURISTICS.update(roles)


def has_heuristics_for_role(role: str | None) -> bool:
    return role in _ROLES_WITH_HEURISTICS


def _matches(step: HeuristicStep) -> bool:
    for fn in step.conditions:
        try:
            if not fn():
                return False
        except Exception:
            return False
    for fn in step.anti_conditions:
        try:
            if fn():
                return False
        except Exception:
            return False
    return True


def _load_providers() -> None:
    from . import ui_deployment  # noqa: F401 — side-effect: registers deployer heuristics
    from . import neo4j          # noqa: F401
    from . import catalog        # noqa: F401


def evaluate() -> list[HeuristicStep]:
    _load_providers()
    return sorted((s for s in _REGISTRY if _matches(s)), key=lambda s: s.order)


def evaluate_state() -> list[tuple[HeuristicStep, list[tuple[str, bool]], list[tuple[str, bool]]]]:
    """Return per-heuristic condition evaluation for diagnostics.

    Each entry is (step, conditions_results, anti_conditions_results) where
    each result is (callable_name, bool_value).
    """
    _load_providers()
    result = []
    for step in sorted(_REGISTRY, key=lambda s: s.order):
        cond_results: list[tuple[str, bool]] = []
        for fn in step.conditions:
            try:
                val = fn()
            except Exception:
                val = False
            cond_results.append((fn.__name__, val))
        anti_results: list[tuple[str, bool]] = []
        for fn in step.anti_conditions:
            try:
                val = fn()
            except Exception:
                val = False
            anti_results.append((fn.__name__, val))
        result.append((step, cond_results, anti_results))
    return result
