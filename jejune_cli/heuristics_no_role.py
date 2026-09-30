"""No-role heuristic registrations."""
from __future__ import annotations

from .heuristic_step import HeuristicStep
from .heuristic_step_registry import HeuristicStepRegistry
from .role_registry import RoleRegistry


def register_heuristics(
    registry: HeuristicStepRegistry,
    role_registry: RoleRegistry,
) -> None:
    def _is_jejune_workspace_cwd() -> bool:
        return bool(role_registry.detect_role())

    registry.register(HeuristicStep(
        label="Connect to a jejune workspace directory",
        command="cd <jejune_doc_or_deploy_dir>",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})

    registry.register(HeuristicStep(
        label="Create document workspace directory",
        command="jejune document init --help",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})

    registry.register(HeuristicStep(
        label="Create deployment workspace directory",
        command="jejune deployment init --help",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})
