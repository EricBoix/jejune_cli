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
    order: int
    conditions: list[Callable[[], bool]] = field(default_factory=list)
    anti_conditions: list[Callable[[], bool]] = field(default_factory=list)

    def resolved_command(self) -> str | None:
        return self.command() if callable(self.command) else self.command


_REGISTRY: list[HeuristicStep] = []
_ROLES_WITH_HEURISTICS: set[str] = set()
_PRECONDITIONS: dict[str, Callable[[], bool]] = {}


def register_command_precondition(command: str, check: Callable[[], bool]) -> None:
    _PRECONDITIONS[command] = check


def command_viable(command: str) -> bool:
    """Return True if no precondition is registered or the registered check passes."""
    check = _PRECONDITIONS.get(command)
    if check is None:
        return True
    try:
        return bool(check())
    except Exception:
        return False


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


def evaluate(cwd: Path | None = None) -> list[HeuristicStep]:
    _load_providers()
    if cwd is None:
        return sorted(
            (s for s in _REGISTRY if _matches(s) and (s.command is None or command_viable(s.command))),
            key=lambda s: s.order,
        )
    old = os.getcwd()
    try:
        os.chdir(cwd)
        return sorted(
            (s for s in _REGISTRY if _matches(s) and (s.command is None or command_viable(s.command))),
            key=lambda s: s.order,
        )
    finally:
        os.chdir(old)


def print_next_steps(cwd: Path | None = None) -> None:
    """Evaluate and print heuristic next steps. Silent if none apply."""
    steps = evaluate(cwd)
    if not steps:
        return
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

    def _run() -> list[tuple[HeuristicStep, list[tuple[str, bool]], list[tuple[str, bool]]]]:
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

    if cwd is None:
        return _run()
    old = os.getcwd()
    try:
        os.chdir(cwd)
        return _run()
    finally:
        os.chdir(old)
