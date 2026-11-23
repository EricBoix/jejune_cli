"""Catalog-contributor-role heuristic registrations."""

from __future__ import annotations

from jejune_cli.core.component_containerized import ContComp
from jejune_cli.core.component_registry import ComponentRegistry
from jejune_cli.roles.heuristic_step import HeuristicStep
from jejune_cli.roles.heuristic_step_registry import HeuristicStepRegistry
from jejune_cli.roles.role_registry import RoleRegistry


def register_heuristics(
    registry: HeuristicStepRegistry,
    component_registry: ComponentRegistry,
    role_registry: RoleRegistry,
) -> None:
    def _any_buildable_image_missing() -> bool:
        active = role_registry.active_components(role_registry.detect_role())
        return any(
            not inst.is_built()
            for inst in active
            if isinstance(inst, ContComp) and not inst.is_external_image
        )

    registry.register(
        HeuristicStep(
            label="run `jejune build`",
            command="jejune build",
            conditions=[_any_buildable_image_missing],
            anti_conditions=[],
        ),
        roles={"catalog-contributor"},
    )

    registry.register(
        HeuristicStep(
            label="run `jejune converters test`",
            command="jejune converters test",
            conditions=[],
            anti_conditions=[_any_buildable_image_missing],
        ),
        roles={"catalog-contributor"},
    )
