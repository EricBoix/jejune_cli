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
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Fetch and reset .jejune/tmp repos to their remote HEAD before building.",
)
@click.pass_obj
def build_cmd(app: AppContext, no_cache: bool, update: bool) -> None:
    """Build Docker images for all components in the current role.

    Each component that owns a Docker image registers its builder automatically.
    Use `jejune deployment build <dir>` to build a specific deployment directory.
    """
    active_role_obj = app.role_registry.detect_role()
    if update:
        app.component_registry.get("ecosystem").update_all_tmp_repos()
    if app.role_registry.role_is_deployer_family(active_role_obj):
        raise SystemExit(
            app.component_registry.get("deployment").build(Path("."), no_cache=no_cache)
        )
    role_comps = app.role_registry.role_components(active_role_obj) or frozenset()
    all_active = app.component_registry.sorted_active_set(role_comps)
    builders = [
        inst
        for inst in all_active
        if isinstance(inst, ContComp) and not inst.is_external_image
    ]
    if not builders:
        raise click.UsageError(
            f"'jejune build' has no Docker images registered for role {active_role_obj.name or None!r}."
        )
    for inst in builders:
        inst.build(no_cache)
