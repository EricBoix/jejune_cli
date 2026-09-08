"""No-role heuristic registrations."""
from __future__ import annotations

from .heuristic_step import HeuristicStep
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY


def _is_jejune_workspace_cwd() -> bool:
    from .role_registry import ROLE_REGISTRY
    return bool(ROLE_REGISTRY.detect_role())


def register_heuristics() -> None:
    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Connect to a jejune workspace directory",
        command="cd <jejune_doc_or_deploy_dir>",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Create document workspace directory",
        command="jejune document init --help",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Create deployment workspace directory",
        command="jejune deployment init --help",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})
