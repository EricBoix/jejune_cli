from pathlib import Path

import click

from .component_registry import REGISTRY as COMP_REGISTRY
from .role_registry import ROLE_REGISTRY


@click.command("build")
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Do not use cache when building images.",
)
def build_cmd(no_cache: bool) -> None:
    """Build Docker images for all components in the current role.

    Each component that owns a Docker image registers its builder automatically.
    Use `jejune deployment build <dir>` to build a specific deployment directory.
    """
    active_role_obj = ROLE_REGISTRY.detect_role()
    if ROLE_REGISTRY.role_inherits(active_role_obj, "deployer"):
        raise SystemExit(COMP_REGISTRY.get("deployment").build(Path("."), no_cache=no_cache))
    from .component_containerized import cont_comp

    active_components = ROLE_REGISTRY.role_components(active_role_obj) or set()
    component_names = {comp.name for comp in active_components}
    builders = [
        inst
        for inst in COMP_REGISTRY
        if isinstance(inst, cont_comp)
        and inst.name in component_names
        and (inst.build_context or getattr(inst, "repos", None))
    ]
    if not builders:
        raise click.UsageError(
            f"'jejune build' has no Docker images registered for role {active_role_obj.name or None!r}."
        )
    for inst in builders:
        inst.build(no_cache)
