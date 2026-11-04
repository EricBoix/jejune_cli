"""Unit tests for HeuristicStepRegistry: once-per-AppContext next-steps printing."""

from __future__ import annotations

import pytest

from jejune_cli.heuristic_step import HeuristicStep
from jejune_cli.heuristic_step_registry import HeuristicStepRegistry


class StubRoleRegistry:
    def detect_role_name(self) -> str | None:
        return None


class TestHeuristicStepRegistry:
    @staticmethod
    def make_registry() -> HeuristicStepRegistry:
        registry = HeuristicStepRegistry(StubRoleRegistry())  # type: ignore[arg-type]
        registry.register(HeuristicStep(label="Do the thing", command=None), {None})
        return registry

    def test_print_next_steps_prints_once(self, capsys: pytest.CaptureFixture) -> None:
        registry = self.make_registry()

        registry.print_next_steps()
        first_output = capsys.readouterr().out
        registry.print_next_steps()
        second_output = capsys.readouterr().out

        assert "Do the thing" in first_output
        assert second_output == ""

    def test_suppress_next_steps_silences_print(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        registry = self.make_registry()

        registry.suppress_next_steps()
        registry.print_next_steps()

        assert capsys.readouterr().out == ""
