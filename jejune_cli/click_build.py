from pathlib import Path

import click

from .app_context import AppContext
from .component_containerized import ContComp


@click.command("build")
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Do not use cache when building images.",
)
@click.pass_obj
def build_cmd(app: AppContext, no_cache: bool) -> None:
    """Build Docker images for all components in the current role.

    Each component that owns a Docker image registers its builder automatically.
    Use `jejune deployment build <dir>` to build a specific deployment directory.
    """
    active_role_obj = app.role_registry.detect_role()
    if app.role_registry.role_is_deployer_family(active_role_obj):
        raise SystemExit(
            app.component_registry.get("deployment").build(Path("."), no_cache=no_cache)
        )
    active_components = app.role_registry.role_components(active_role_obj) or set()
    component_names = {comp.name for comp in active_components}
    builders = [
        inst
        for inst in app.component_registry
        if isinstance(inst, ContComp)
        and inst.name in component_names
        and (inst.build_context or getattr(inst, "repos", None))
    ]
    if not builders:
        raise click.UsageError(
            f"'jejune build' has no Docker images registered for role {active_role_obj.name or None!r}."
        )
    for inst in builders:
        inst.build(no_cache)
