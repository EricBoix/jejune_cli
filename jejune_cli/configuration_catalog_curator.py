"""Catalog-curator role: configuration data and workspace initialisation."""

import shutil
from pathlib import Path

import click

from ._env import dot_jejune

_TEMPLATES = Path(__file__).parent / "templates" / "catalog-curator"

CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {}
COMPONENT_CONFIG_HINTS: dict[str, str] = {}


@click.command("init")
def init() -> None:
    """Write catalog-curator scaffold files into .jejune/ in the current directory.

    Creates .jejune/role and .jejune/env-config from built-in templates.
    Adds .jejune to .gitignore so the whole directory stays local by default.
    """
    d = dot_jejune()
    d.mkdir(exist_ok=True)

    created = []
    skipped = []
    for fname in ("role", "env-config"):
        dst = d / fname
        if dst.exists():
            skipped.append(fname)
        else:
            shutil.copy2(_TEMPLATES / fname, dst)
            created.append(fname)

    for f in created:
        click.echo(click.style(f"  created  .jejune/{f}", fg="green"))
    for f in skipped:
        click.echo(click.style(f"  skipped  .jejune/{f} (already exists)", fg="yellow"))

    gitignore = Path.cwd() / ".gitignore"
    if not gitignore.exists() or ".jejune" not in gitignore.read_text().splitlines():
        with gitignore.open("a") as fh:
            fh.write(".jejune\n")
        click.echo(click.style("  updated  .gitignore (.jejune)", fg="green"))

    click.echo()
    click.echo(
        "Next step: optionally set JEJUNE_ROOT_DIR in .jejune/env-config "
        "to point to your local clones directory."
    )
