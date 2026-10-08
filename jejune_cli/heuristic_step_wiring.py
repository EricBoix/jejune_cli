"""Explicit heuristic wiring — called by AppContext.__init__."""

from __future__ import annotations

from .component_registry import ComponentRegistry
from .dot_jejune import DotJejune
from .heuristic_step_registry import HeuristicStepRegistry
from .role_registry import RoleRegistry
from . import heuristics_deployer, heuristics_doc_steward, heuristics_no_role


def wire_heuristics(
    registry: HeuristicStepRegistry,
    component_registry: ComponentRegistry,
    role_registry: RoleRegistry,
) -> None:
    """Register all heuristic steps and preconditions."""

    def _doctor_viable() -> bool:
        active_role = role_registry.detect_role_name()
        is_doc_steward_family = active_role is None or role_registry.role_is_doc_steward_family(
            active_role
        )
        return not (is_doc_steward_family and not DotJejune().is_dir())

    registry.register_command_precondition("jejune doctor", _doctor_viable)

    heuristics_deployer.register_heuristics(registry, component_registry)
    heuristics_doc_steward.register_heuristics(registry, component_registry)
    heuristics_no_role.register_heuristics(registry, role_registry)
