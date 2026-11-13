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
from .component_catalog_access_checker import CatalogAccessChecker
from .component_catalog_file import CatalogFile
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
    then check the catalog (when there is one) like check-configuration does.

    Local checks only: the token file(s) are reported well-formed, not accepted
    by the server. Use check-availability to probe the repositories."""
    failed = False
    try:
        print_config_check(comp.configuration)
    except SystemExit:
        failed = True
    catalog_path = CatalogFile.resolve_path(catalog_option)
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


def print_rows(rows: list[tuple[str, str, str]]) -> bool:
    """Print one (status, subject, message) row per line; return True when there
    is no error."""
    subject_width = max((len(subject) for _, subject, _ in rows), default=0)
    colors = {"ok": "green", "warn": "yellow", "error": "red"}
    for status, subject, message in rows:
        label = click.style(f"{status:<5}", fg=colors[status])
        click.echo(f"  {label}  {subject:<{subject_width}}  {message}")
    return not any(status == "error" for status, _, _ in rows)


def print_catalog_check(comp: CompGitAccess, catalog_path: Path) -> bool:
    """Print one row per catalog entry; return True when there is no error."""
    return print_rows(CatalogAccessChecker(comp, catalog_path).run())


@git_access.command("check-configuration")
@CATALOG_OPTION
@click.pass_obj
def check_configuration(comp, catalog_option):
    """Check that catalog.yaml and the access-key files it points to agree and that
    the token file(s) are well-formed.

    A private entry (`public: false`) needs a well-formed token file: its own
    `token_file`, else the one of the environment. Local checks only: neither
    the urls nor the acceptance of the keys by the server are checked (see
    check-availability). Exits 1 on any error.
    """
    if not print_catalog_check(
        comp, CatalogFile.resolve_path(catalog_option)
    ):
        raise SystemExit(1)


@git_access.command("check-availability")
@CATALOG_OPTION
@click.pass_context
def check_availability(ctx, catalog_option):
    """Show git-access availability detail (environment variables and catalog entries).

    After the local checks of check-configuration, every catalog entry is probed
    on the network (`git ls-remote` with the key of the entry): `reachable`, or
    `not reachable: wrong url or no access`. The ecosystem repositories that are
    not cloned locally are probed the same way, with the credentials of the
    environment. Exits 1 on any error.
    """
    comp = ctx.obj
    catalog_path = CatalogFile.resolve_path(catalog_option)
    status, message = comp.check()
    label = "ok" if status == "ok" else message
    click.echo(
        f"  access  {click.style(label, fg=ClickTheme.status_foregrounds.get(status, 'white'))}"
    )
    all_ok = True
    if catalog_option or catalog_path.is_file():
        click.echo()
        local_ok = print_catalog_check(comp, catalog_path)
        click.echo()
        click.echo("Remote probing the repository")
        probe_ok = print_rows(CatalogAccessChecker(comp, catalog_path).probe_remote())
        all_ok = local_ok and probe_ok
    ecosystem_rows = ecosystem_probe_rows(ctx.find_object(AppContext))
    if ecosystem_rows:
        click.echo()
        click.echo("Remote probing the ecosystem")
        all_ok = print_rows(ecosystem_rows) and all_ok
    if not all_ok:
        raise SystemExit(1)


def ecosystem_probe_rows(app: AppContext) -> list[tuple[str, str, str]]:
    """One (status, subject, message) row per ecosystem repository that is not
    cloned locally: whether its remote can be reached."""
    ecosystem = app.component_registry.get("ecosystem")
    role = app.role_registry.detect_role()
    active = app.role_registry.role_components(role)
    states = ecosystem.repository_states(
        (
            []
            if active is None
            else [comp for comp in app.component_registry if comp in active]
        ),
        ecosystem.resolve_dirs(),
    )
    return [
        (
            "ok" if state.reachable else "error",
            state.name,
            (
                f"reachable ({state.remote_url})"
                if state.reachable
                else f"not reachable: wrong url or no access ({state.remote_url})"
            ),
        )
        for state in states
        if not state.location.is_local
    ]


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
        click.echo(click.style("all access keys found and well-formed", fg="green"))
    else:
        click.echo("run `jejune git-access check-availability`")
