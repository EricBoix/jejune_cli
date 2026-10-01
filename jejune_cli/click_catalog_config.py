"""Configuration init subgroup for the catalog-contributor role.

Provides `jejune configuration catalog-contributor init`, which
scaffolds the workspace files (.jejune/role, .jejune/ecosystem-env-config).
"""

import shutil
from pathlib import Path

import click

from ._package_paths import TemplatePaths
from .app_context import AppContext
from .dot_jejune import DotJejune


@click.command("init")
def curator_init() -> None:
    """Write catalog-contributor scaffold files into .jejune/ in the current directory.

    Creates .jejune/role and .jejune/ecosystem-env-config from built-in templates.
    Adds .jejune to .gitignore so the whole directory stays local by default.
    """
    dot_jejune = DotJejune()
    dot_jejune.mkdir(exist_ok=True)

    created = []
    skipped = []

    role_dst = dot_jejune / "role"
    if role_dst.exists():
        skipped.append("role")
    else:
        role_dst.write_text("catalog-contributor\n")
        created.append("role")

    eco_dst = dot_jejune / "ecosystem-env-config"
    if eco_dst.exists():
        skipped.append("ecosystem-env-config")
    else:
        shutil.copy2(TemplatePaths.ECOSYSTEM_ENV_CONFIG, eco_dst)
        created.append("ecosystem-env-config")

    for fname in created:
        click.echo(click.style(f"  created  .jejune/{fname}", fg="green"))
    for fname in skipped:
        click.echo(
            click.style(f"  skipped  .jejune/{fname} (already exists)", fg="yellow")
        )

    gitignore = Path.cwd() / ".gitignore"
    if not gitignore.exists() or ".jejune" not in gitignore.read_text().splitlines():
        with gitignore.open("a") as fh:
            fh.write(".jejune\n")
        click.echo(click.style("  updated  .gitignore (.jejune)", fg="green"))

    app = click.get_current_context().find_object(AppContext)
    app.heuristic_step_registry.print_next_steps()


@click.group(
    "catalog-contributor", short_help="Collection-catalog-contributor role workspace"
)
def curator_config_group():
    """Initialise and inspect the catalog-contributor workspace."""


curator_config_group.add_command(curator_init, "init")
