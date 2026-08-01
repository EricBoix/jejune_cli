"""Heuristic next-step guidance for jejune CLI commands."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import click


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


_REGISTRY: list[HeuristicStep] = []
_ROLES_WITH_HEURISTICS: set[str | None] = set()
_PRECONDITIONS: dict[str, Callable[[], bool]] = {}
_NAMED_PRECONDITIONS: dict[str, Callable[[], bool]] = {}
_ROLE_ORDERINGS: dict[str | None, dict[str, int]] = {}
_next_steps_printed: bool = False


def register_command_precondition(command: str, check: Callable[[], bool]) -> None:
    _PRECONDITIONS[command] = check


def register_precondition(name: str, check: Callable[[], bool]) -> None:
    _NAMED_PRECONDITIONS[name] = check


def command_viable(command: str) -> bool:
    """Return True if no precondition is registered or the registered check passes."""
    check = _PRECONDITIONS.get(command)
    if check is None:
        return True
    try:
        return bool(check())
    except Exception:
        return False


def register_role_ordering(role: str | None, ordering: dict[str, int]) -> None:
    _ROLE_ORDERINGS[role] = ordering


def register_heuristic(step: HeuristicStep, roles: set[str | None]) -> None:
    step.roles = frozenset(roles)
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


def _step_viable(s: HeuristicStep) -> bool:
    return callable(s.command) or s.command is None or command_viable(s.command)


def _role_specificity(step: HeuristicStep, active_role: str | None) -> int:
    """Number of roles beyond the active role. Lower = more specific = sorted first."""
    return len(step.roles - {None, active_role})


def _condition_count(step: HeuristicStep) -> int:
    """Total number of conditions + anti-conditions. Higher = more specific = sorted first."""
    return len(step.conditions) + len(step.anti_conditions)


def _sort_key(
    step: HeuristicStep,
    active_role: str | None,
    ordering: dict[str, int] | None,
) -> tuple:
    rule3 = ordering.get(step.label, 0) if ordering else 0
    return (rule3, _role_specificity(step, active_role), -_condition_count(step), step.order)


def _effective_ordering(
    active_role: str | None,
    ordering: dict[str, int] | None,
) -> dict[str, int] | None:
    """Explicit ordering overrides role ordering; role ordering is the fallback."""
    return ordering if ordering is not None else _ROLE_ORDERINGS.get(active_role)


def evaluate(
    cwd: Path | None = None,
    ordering: dict[str, int] | None = None,
) -> list[HeuristicStep]:
    _load_providers()
    from .role import detect_role

    def _sorted(active_role: str | None) -> list[HeuristicStep]:
        eff = _effective_ordering(active_role, ordering)
        def _key(s: HeuristicStep) -> tuple:
            return _sort_key(s, active_role, eff)
        return sorted(
            (s for s in _REGISTRY if _matches(s) and _step_viable(s)),
            key=_key,
        )

    if cwd is None:
        active_role, _ = detect_role()
        return _sorted(active_role)
    old = os.getcwd()
    try:
        os.chdir(cwd)
        active_role, _ = detect_role()
        return _sorted(active_role)
    finally:
        os.chdir(old)


def print_next_steps(
    cwd: Path | None = None,
    ordering: dict[str, int] | None = None,
) -> None:
    """Evaluate and print heuristic next steps. Silent if none apply."""
    global _next_steps_printed
    if _next_steps_printed:
        return
    steps = evaluate(cwd, ordering=ordering)
    if not steps:
        return
    _next_steps_printed = True
    click.echo()
    if cwd is not None and cwd.resolve() != Path.cwd().resolve():
        click.echo(f"Next steps (from {cwd.name}/):")
    else:
        click.echo("Next steps:")
    for s in steps:
        cmd = s.resolved_command()
        suffix = f"  →  {cmd}" if cmd else ""
        click.echo(f"  • {s.label}{suffix}")


def evaluate_state(cwd: Path | None = None) -> list[tuple[HeuristicStep, list[tuple[str, bool]], list[tuple[str, bool]]]]:
    """Return per-heuristic condition evaluation for diagnostics."""
    _load_providers()
    from .role import detect_role
    active_role, _ = detect_role()

    def _run() -> list[tuple[HeuristicStep, list[tuple[str, bool]], list[tuple[str, bool]]]]:
        result = []
        for step in sorted(_REGISTRY, key=lambda s: _sort_key(s, active_role)):
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

    if cwd is None:
        return _run()
    old = os.getcwd()
    try:
        os.chdir(cwd)
        return _run()
    finally:
        os.chdir(old)
