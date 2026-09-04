"""Doc-steward role: configuration data and workspace initialisation."""

import shutil
from pathlib import Path

import click

from ._env import dot_jejune
from .extensions_registry import _do_extensions_install, _extensions_installed
from .next_steps import print_next_steps

_TEMPLATES = Path(__file__).parent / "templates" / "doc-steward"
_ECOSYSTEM_TEMPLATE = Path(__file__).parent / "templates" / "ecosystem" / "env-config"

class _DocStewardInit(click.Command):
    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write_usage(
            ctx.command_path,
            "[OPTIONS] [DIR_NAME]",
            prefix="Usage [doc-steward]: ",
        )


@click.command("init", cls=_DocStewardInit)
@click.argument("dir_name", required=False, metavar="DIR_NAME")
def init(dir_name: str | None) -> None:
    """Write jejune scaffold files into .jejune/ in DIR_NAME.

    DIR_NAME defaults to the current directory when omitted.
    Creates .jejune/env-config, .jejune/env-secrets, and .jejune/ecosystem-env-config
    from built-in templates.
    Adds .jejune to .gitignore so the whole directory stays local by default.
    """
    target = Path(dir_name) if dir_name else Path.cwd()
    d = dot_jejune(target)
    d.mkdir(exist_ok=True)

    created = []
    skipped = []
    for fname in ("env-config", "env-secrets", "role"):
        dst = d / fname
        if dst.exists():
            skipped.append(fname)
        else:
            shutil.copy2(_TEMPLATES / fname, dst)
            created.append(fname)

    eco_dst = d / "ecosystem-env-config"
    if eco_dst.exists():
        skipped.append("ecosystem-env-config")
    else:
        shutil.copy2(_ECOSYSTEM_TEMPLATE, eco_dst)
        created.append("ecosystem-env-config")

    for f in created:
        click.echo(click.style(f"  created  .jejune/{f}", fg="green"))
    for f in skipped:
        click.echo(click.style(f"  skipped  .jejune/{f} (already exists)", fg="yellow"))

    gitignore = target / ".gitignore"
    entry = ".jejune\n"
    if not gitignore.exists() or ".jejune" not in gitignore.read_text().splitlines():
        with gitignore.open("a") as fh:
            fh.write(entry)
        click.echo(click.style("  updated  .gitignore (.jejune)", fg="green"))

    if not _extensions_installed(role="doc-steward"):
        click.echo("\nInstalling catalog-contributor extension...")
        _do_extensions_install(role="doc-steward")

    cd_hint = None
    if dir_name and dir_name not in (".", str(Path.cwd())) and target.resolve() != Path.cwd().resolve():
        cd_hint = [f"First: cd {dir_name}"]
    print_next_steps(preamble=cd_hint)


@click.group("doc-steward", short_help="Doc-steward role workspace")
def doc_steward_group():
    """Initialise and inspect the doc-steward workspace."""


doc_steward_group._role_subgroup = True
doc_steward_group.add_command(init, "init")
