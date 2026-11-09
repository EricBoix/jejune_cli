"""The `jejune git-access` command group."""

from pathlib import Path

import click

from .app_context import AppContext
from .click_configuration import (
    print_config_check,
    print_config_hint,
    print_config_status,
)
from .click_theme import ClickTheme
from .component_git_access import CompGitAccess

CATALOG_OPTION = click.option(
    "--catalog",
    "catalog_option",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Catalog file to check (default: $JEJUNE_CATALOG or ./catalog.yaml).",
)


@click.group(short_help="Git authentication to repositories")
@click.pass_context
def git_access(ctx):
    """Manage how git authenticates to repository URLs."""
    ctx.obj = ctx.find_object(AppContext).component_registry.get("git-access")


@git_access.command("check-config")
@CATALOG_OPTION
@click.pass_obj
def check_config(comp, catalog_option):
    """Show per-variable configuration detail for the git-access component,
    then check the catalog (when there is one) like check-configuration does."""
    failed = False
    try:
        print_config_check(comp.configuration)
    except SystemExit:
        failed = True
    catalog_path = CompGitAccess.resolve_catalog_path(catalog_option)
    if catalog_option or catalog_path.is_file():
        click.echo()
        failed = not print_catalog_check(comp, catalog_path) or failed
    if failed:
        raise SystemExit(1)


@git_access.command("status-config")
@click.pass_obj
def status_config(comp):
    """Show git-access configuration status."""
    print_config_status(comp.configuration)


@git_access.command("hint-config")
@click.pass_obj
def hint_config(comp):
    """Show the configuration hint for the git-access component."""
    print_config_hint(comp.configuration)


def print_catalog_check(comp: CompGitAccess, catalog_path: Path) -> bool:
    """Print one row per catalog entry; return True when there is no error."""
    rows = comp.check_catalog(catalog_path)
    subject_width = max(len(subject) for _, subject, _ in rows)
    colors = {"ok": "green", "warn": "yellow", "error": "red"}
    for status, subject, message in rows:
        label = click.style(f"{status:<5}", fg=colors[status])
        click.echo(f"  {label}  {subject:<{subject_width}}  {message}")
    return not any(status == "error" for status, _, _ in rows)


@git_access.command("check-configuration")
@CATALOG_OPTION
@click.pass_obj
def check_configuration(comp, catalog_option):
    """Check that catalog.yaml and the access-key files it points to agree and are valid.

    A private entry (`public: false`) needs a valid token file: its own
    `token_file`, else the one of the environment. Exits 1 on any error.
    """
    if not print_catalog_check(
        comp, CompGitAccess.resolve_catalog_path(catalog_option)
    ):
        raise SystemExit(1)


@git_access.command("check-availability")
@CATALOG_OPTION
@click.pass_obj
def check_availability(comp, catalog_option):
    """Show git-access availability detail (environment variables and catalog entries)."""
    catalog_path = CompGitAccess.resolve_catalog_path(catalog_option)
    status, message = comp.check()
    label = "ok" if status == "ok" else message
    click.echo(
        f"  access  {click.style(label, fg=ClickTheme.status_foregrounds.get(status, 'white'))}"
    )
    if catalog_option or catalog_path.is_file():
        click.echo()
        if not print_catalog_check(comp, catalog_path):
            raise SystemExit(1)


@git_access.command("status-availability")
@click.pass_obj
def status_availability(comp):
    """Show git-access availability status."""
    status, _ = comp.check()
    click.echo(
        f"git-access: {click.style(status, fg=ClickTheme.status_foregrounds.get(status, 'white'))}"
    )


@git_access.command("hint-availability")
@click.pass_obj
def hint_availability(comp):
    """Show how to fix git-access availability issues."""
    status, _ = comp.check()
    if status == "ok":
        click.echo(click.style("all access keys found and valid", fg="green"))
    else:
        click.echo("run `jejune git-access check-availability`")
