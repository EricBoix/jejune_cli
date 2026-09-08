"""HeuristicStepRegistry singleton."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import click

from .heuristic_step import HeuristicStep


class HeuristicStepRegistry:
    def __init__(self) -> None:
        self._steps: list[HeuristicStep] = []
        self._roles_with_heuristics: set[str | None] = set()
        self._command_preconditions: dict[str, Callable[[], bool]] = {}
        self._named_preconditions: dict[str, Callable[[], bool]] = {}
        self._role_orderings: dict[str | None, dict[str, int]] = {}
        self._next_steps_printed: bool = False
        self._providers_loaded: bool = False

    def register_command_precondition(self, command: str, check: Callable[[], bool]) -> None:
        self._command_preconditions[command] = check

    def register_precondition(self, name: str, check: Callable[[], bool]) -> None:
        self._named_preconditions[name] = check

    @property
    def named_preconditions(self) -> dict[str, Callable[[], bool]]:
        return self._named_preconditions

    @property
    def command_preconditions(self) -> dict[str, Callable[[], bool]]:
        return self._command_preconditions

    def command_viable(self, command: str) -> bool:
        check = self._command_preconditions.get(command)
        if check is None:
            return True
        try:
            return bool(check())
        except Exception:
            return False

    def register_role_ordering(self, role: str | None, ordering: dict[str, int]) -> None:
        self._role_orderings[role] = ordering

    def register(self, step: HeuristicStep, roles: set[str | None]) -> None:
        step.roles = frozenset(roles)
        self._steps.append(step)
        self._roles_with_heuristics.update(roles)

    def has_heuristics_for_role(self, role: str | None) -> bool:
        return role in self._roles_with_heuristics

    def _load_providers(self) -> None:
        if self._providers_loaded:
            return
        self._providers_loaded = True
        from . import heuristics_deployer, heuristics_doc_steward, heuristics_no_role
        heuristics_deployer.register_heuristics()
        heuristics_doc_steward.register_heuristics()
        heuristics_no_role.register_heuristics()

    def _matches(self, step: HeuristicStep) -> bool:
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

    def _step_viable(self, s: HeuristicStep) -> bool:
        return callable(s.command) or s.command is None or self.command_viable(s.command)

    def _role_specificity(self, step: HeuristicStep, active_role: str | None) -> int:
        return len(step.roles - {None, active_role})

    def _condition_count(self, step: HeuristicStep) -> int:
        return len(step.conditions) + len(step.anti_conditions)

    def _sort_key(
        self,
        step: HeuristicStep,
        active_role: str | None,
        ordering: dict[str, int] | None,
    ) -> tuple:
        rule3 = ordering.get(step.label, 0) if ordering else 0
        return (rule3, step.order, self._role_specificity(step, active_role), -self._condition_count(step))

    def _effective_ordering(
        self,
        active_role: str | None,
        ordering: dict[str, int] | None,
    ) -> dict[str, int] | None:
        return ordering if ordering is not None else self._role_orderings.get(active_role)

    def evaluate(
        self,
        cwd: Path | None = None,
        ordering: dict[str, int] | None = None,
    ) -> list[HeuristicStep]:
        self._load_providers()
        from .role_registry import ROLE_REGISTRY

        def _sorted(active_role: str | None) -> list[HeuristicStep]:
            eff = self._effective_ordering(active_role, ordering)
            def _key(s: HeuristicStep) -> tuple:
                return self._sort_key(s, active_role, eff)
            return sorted(
                (s for s in self._steps if self._matches(s) and self._step_viable(s)),
                key=_key,
            )

        if cwd is None:
            return _sorted(ROLE_REGISTRY.detect_role().name or None)
        old = os.getcwd()
        try:
            os.chdir(cwd)
            return _sorted(ROLE_REGISTRY.detect_role().name or None)
        finally:
            os.chdir(old)

    def print_next_steps(
        self,
        cwd: Path | None = None,
        ordering: dict[str, int] | None = None,
        preamble: list[str] | None = None,
    ) -> None:
        """Evaluate and print heuristic next steps. Silent if none apply."""
        if self._next_steps_printed:
            return
        steps = self.evaluate(cwd, ordering=ordering)
        if not steps and not preamble:
            return
        self._next_steps_printed = True
        click.echo()
        if cwd is not None and cwd.resolve() != Path.cwd().resolve():
            title = f"Next steps (from {cwd.name}/)"
        else:
            title = "Next steps"
        click.echo(click.style(f"  {title}", bold=True))
        click.echo("  " + "─" * len(title))
        if preamble:
            for line in preamble:
                click.echo(f"  {line}")
        if preamble and steps:
            click.echo(f"  Then:")
        for s in steps:
            cmd = s.resolved_command()
            suffix = f"  →  {cmd}" if cmd else ""
            click.echo(f"  • {s.label}{suffix}")

    def evaluate_state(
        self,
        cwd: Path | None = None,
    ) -> list[tuple[HeuristicStep, list[tuple[str, bool]], list[tuple[str, bool]]]]:
        """Return per-heuristic condition evaluation for diagnostics."""
        self._load_providers()
        from .role_registry import ROLE_REGISTRY
        active_role = ROLE_REGISTRY.detect_role().name or None

        def _run() -> list[tuple[HeuristicStep, list[tuple[str, bool]], list[tuple[str, bool]]]]:
            result = []
            for step in sorted(self._steps, key=lambda s: self._sort_key(s, active_role, None)):
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


HEURISTIC_STEP_REGISTRY = HeuristicStepRegistry()
