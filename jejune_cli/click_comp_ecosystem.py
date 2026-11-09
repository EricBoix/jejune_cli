"""The `jejune ecosystem` command group."""

import click
from pathlib import Path

from .app_context import AppContext
from .click_theme import ClickTheme
from .component_ecosystem import CompEcosystem, UpdateOutcome
from .component_git_access import CompGitAccess


@click.group(invoke_without_command=True, short_help="Ecosystem repository status")
@click.pass_context
def ecosystem(ctx: click.Context) -> None:
    """Show ecosystem repository resolution status."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(ecosystem_status)


@ecosystem.command("status")
@click.pass_context
def ecosystem_status(ctx) -> None:
    """List required repositories and their local/remote resolution status."""
    app = ctx.find_object(AppContext)
    eco = app.component_registry.get("ecosystem")
    role = app.role_registry.detect_role()
    root_dir, tmp_dir = eco.resolve_dirs()

    role_label = f"  [{role.name}]" if role else ""
    click.echo(f"jejune ecosystem{role_label}")
    click.echo()

    # --- Environment header ---
    _W = 15  # width of label column

    root_val = str(root_dir) if root_dir else click.style("(not set)", fg="yellow")
    root_ok = root_dir is not None and root_dir.is_dir()
    root_status = (
        click.style("set", fg="green")
        if root_ok
        else click.style("not set", fg="yellow")
    )
    click.echo(f"  {'JEJUNE_ROOT_DIR':<{_W}}  {root_val:<50}  {root_status}")

    click.echo(
        f"  {'REPO_ROOT_DIR':<{_W}}  {app.component_registry.get('git-server').repo_root_dir()}"
    )
    click.echo()

    # --- Components table ---
    active = app.role_registry.role_components(role)
    repos = (
        []
        if active is None
        else [
            (comp, subpath, env_key)
            for comp in app.component_registry
            if comp in active
            for subpath, env_key in getattr(comp, "repos", [])
        ]
    )
    click.echo(click.style("  Components", bold=True))
    if not repos:
        click.echo(
            click.style(
                "    No repositories required for the current role.", fg="yellow"
            )
        )
    else:
        rows: list[tuple[str, bool, str, str, bool | None]] = []
        for comp, _, _ in repos:
            # The following makes the assumption that every component that sets
            # self.repos lives in a plugin repo (which might be a latent
            # fragility e.g. for future built-in components)
            name = app.plugin_registry.repo_name_for_plugin(comp.name) or comp.name
            tier, base = eco.repo_status(name, root_dir, tmp_dir)
            if tier == "root":
                clone_display, remote_display = "[JEJUNE_ROOT_DIR]", ""
            elif tier == "tmp":
                clone_display, remote_display = "[.jejune/tmp]", ""
            else:
                clone_display, remote_display = "", "[REPO_ROOT_DIR]"
            up_to_date: bool | None = (
                eco.repo_up_to_date(Path(base)) if tier in ("root", "tmp") else None
            )
            rows.append(
                (
                    name,
                    tier in ("root", "tmp"),
                    clone_display,
                    remote_display,
                    up_to_date,
                )
            )

        _ICON_W = 1  # display width of ✓/✗
        _W_N = max(len("Component"), max(len(r[0]) for r in rows))
        _W_C = max(len("Clone directory"), max(len(r[2]) for r in rows))
        _W_R = max(len("Remote repo"), max(len(r[3]) for r in rows))
        _W_UTD = len("Up-to-date")
        _UTD_PAD = (_W_UTD - 1) // 2

        click.echo(
            f"  {'Component':<{_W_N}}  {'':>{_ICON_W}}  {'Clone directory':<{_W_C}}  {'Remote repo':<{_W_R}}  Up-to-date"
        )
        click.echo("  " + "─" * (_W_N + 2 + _ICON_W + 2 + _W_C + 2 + _W_R + 2 + _W_UTD))
        for name, found, clone_dir, remote_url, up_to_date in rows:
            icon, fg = ClickTheme.status_icons["ok" if found else "error"]
            status_cell = click.style(icon, fg=fg)
            if up_to_date is True:
                utd_icon, utd_fg = ClickTheme.status_icons["ok"]
            elif up_to_date is False:
                utd_icon, utd_fg = ClickTheme.status_icons["error"]
            else:
                utd_icon, utd_fg = ("", "")
            utd_cell = click.style(utd_icon, fg=utd_fg) if utd_fg else ""
            click.echo(
                f"  {name:<{_W_N}}  {status_cell}  {clone_dir:<{_W_C}}  {remote_url:<{_W_R}}  {'':>{_UTD_PAD}}{utd_cell}"
            )

    # --- Documents table ---
    click.echo()
    click.echo(click.style("  Documents", bold=True))
    doc_repos = eco.discover_doc_repos(root_dir, tmp_dir)
    known_names = {name for name, _, _, _ in doc_repos}
    if not doc_repos:
        click.echo(
            click.style("    No document repositories cloned locally.", fg="yellow")
        )
        _echo_catalog_entries_unknown_to_ecosystem(eco, known_names)
        return

    _CLONE_LABEL = {"root": "[JEJUNE_ROOT_DIR]", "tmp": "[.jejune/tmp]"}
    # Private catalog entries are reached with their own access key, as `update` does
    catalog_path = CompGitAccess.resolve_catalog_path()
    token_files = (
        eco.catalog_token_files(catalog_path) if catalog_path.is_file() else {}
    )
    doc_rows: list[tuple[str, bool, str, bool | None]] = [
        (
            name,
            has_doc,
            _CLONE_LABEL.get(tier, tier),
            eco.repo_up_to_date(Path(path_str), token_files.get(name)),
        )
        for name, tier, path_str, has_doc in doc_repos
    ]
    _ICON_W = 1  # display width of ✓/✗
    _W_DN = max(len("Repository"), max(len(r[0]) for r in doc_rows))
    _W_DC = max(len("Clone directory"), max(len(r[2]) for r in doc_rows))
    _W_UTD = len("Up-to-date")
    _UTD_PAD = (_W_UTD - 1) // 2

    click.echo(
        f"  {'Repository':<{_W_DN}}  {'':>{_ICON_W}}  {'Clone directory':<{_W_DC}}  Up-to-date"
    )
    click.echo("  " + "─" * (_W_DN + 2 + _ICON_W + 2 + _W_DC + 2 + _W_UTD))
    for name, has_doc, clone_dir, up_to_date in doc_rows:
        icon, fg = ClickTheme.status_icons["ok" if has_doc else "error"]
        doc_cell = click.style(icon, fg=fg)
        if up_to_date is True:
            utd_icon, utd_fg = ClickTheme.status_icons["ok"]
        elif up_to_date is False:
            utd_icon, utd_fg = ClickTheme.status_icons["error"]
        else:
            utd_icon, utd_fg = ("", "")
        utd_cell = click.style(utd_icon, fg=utd_fg) if utd_fg else ""
        click.echo(
            f"  {name:<{_W_DN}}  {doc_cell}  {clone_dir:<{_W_DC}}  {'':>{_UTD_PAD}}{utd_cell}"
        )
    _echo_catalog_entries_unknown_to_ecosystem(eco, known_names)


def _echo_catalog_entries_unknown_to_ecosystem(
    eco: CompEcosystem, known_names: set[str]
) -> None:
    """List the catalog entries that are neither in JEJUNE_ROOT_DIR nor in .jejune/tmp."""
    catalog_path = CompGitAccess.resolve_catalog_path()
    click.echo()
    click.echo(click.style("  Catalog", bold=True))
    if not catalog_path.is_file():
        click.echo(click.style(f"    No catalog at {catalog_path}.", fg="yellow"))
        return
    try:
        entry_names = eco.catalog_entry_names(catalog_path)
    except ValueError as exc:
        click.echo(click.style(f"    {catalog_path}: {exc}", fg="yellow"))
        return
    unknown_names = [name for name in entry_names if name not in known_names]
    if not unknown_names:
        click.echo(f"    All entries of {catalog_path} are known to the ecosystem.")
        return
    icon, foreground = ClickTheme.status_icons["error"]
    click.echo(f"    Entries of {catalog_path} unknown to the ecosystem:")
    for name in unknown_names:
        click.echo(f"      {click.style(icon, fg=foreground)}  {name}")
    click.echo("    run `jejune ecosystem update` to clone them")


@ecosystem.command("update")
@click.pass_context
def ecosystem_update(ctx) -> None:
    """Clone or update in .jejune/tmp every entry of the catalog (JEJUNE_CATALOG,
    else ./catalog.yaml), then update the other repos cloned in .jejune/tmp.

    Private entries need an access key (see `jejune git-access check-config`):
    an entry that cannot be pulled is reported and makes the command exit 1.
    """
    app = ctx.find_object(AppContext)
    eco = app.component_registry.get("ecosystem")
    catalog_path = CompGitAccess.resolve_catalog_path()
    outcomes: list[UpdateOutcome] = []
    if catalog_path.is_file():
        outcomes = eco.update_catalog_repos(catalog_path)
    else:
        click.echo(
            click.style(
                f"No catalog at {catalog_path}: only updating .jejune/tmp/.",
                fg="yellow",
            )
        )
    for name, was_updated in eco.update_all_tmp_repos(
        skip_names={outcome.name for outcome in outcomes}
    ):
        outcomes.append(
            UpdateOutcome(name, "updated" if was_updated else "up-to-date")
        )
    if not outcomes:
        click.echo("No repositories found in the catalog nor in .jejune/tmp/.")
        return
    status_foregrounds = {
        "cloned": "green",
        "updated": "green",
        "failed": "red",
        "skipped": "yellow",
    }
    for outcome in outcomes:
        status = click.style(
            outcome.status, fg=status_foregrounds.get(outcome.status, "white")
        )
        detail = f" ({outcome.message})" if outcome.message else ""
        click.echo(f"  {outcome.name}: {status}{detail}")
    failed_count = sum(outcome.status == "failed" for outcome in outcomes)
    if failed_count:
        click.echo(
            click.style(
                f"{failed_count} repositories could not be pulled "
                f"(see above): "
                "run `jejune git-access check-config`.",
                fg="red",
            ),
            err=True,
        )
        ctx.exit(1)
