"""The `jejune ecosystem` command group."""

import click
from pathlib import Path

from .app_context import AppContext
from .click_theme import ClickTheme
from .component_ecosystem import CompEcosystem


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
    root_ok  = root_dir is not None and root_dir.is_dir()
    root_status = click.style("set", fg="green") if root_ok else click.style("not set", fg="yellow")
    click.echo(f"  {'JEJUNE_ROOT_DIR':<{_W}}  {root_val:<50}  {root_status}")

    click.echo(f"  {'REPO_ROOT_DIR':<{_W}}  {app.component_registry.get('git-server').repo_root_dir()}")
    click.echo()

    # --- Components table ---
    active = app.role_registry.role_components(role)
    repos = [] if active is None else [
        (comp, subpath, env_key)
        for comp in app.component_registry if comp in active
        for subpath, env_key in getattr(comp, "repos", [])
    ]
    click.echo(click.style("  Components", bold=True))
    if not repos:
        click.echo(click.style("    No repositories required for the current role.", fg="yellow"))
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
            uptodate: bool | None = (
                CompEcosystem.repo_uptodate(Path(base)) if tier in ("root", "tmp") else None
            )
            rows.append((name, tier in ("root", "tmp"), clone_display, remote_display, uptodate))

        _ICON_W = 1  # display width of ✓/✗
        _W_N = max(len("Component"),       max(len(r[0]) for r in rows))
        _W_C = max(len("Clone directory"), max(len(r[2]) for r in rows))
        _W_R = max(len("Remote repo"),     max(len(r[3]) for r in rows))
        _W_UTD = len("Up-to-date")

        click.echo(f"  {'Component':<{_W_N}}  {'':>{_ICON_W}}  {'Clone directory':<{_W_C}}  {'Remote repo':<{_W_R}}  Up-to-date")
        click.echo("  " + "─" * (_W_N + 2 + _ICON_W + 2 + _W_C + 2 + _W_R + 2 + _W_UTD))
        for name, found, clone_dir, remote_url, uptodate in rows:
            icon, fg = ClickTheme.status_icons["ok" if found else "error"]
            status_cell = click.style(icon, fg=fg)
            if uptodate is True:
                utd_icon, utd_fg = ClickTheme.status_icons["ok"]
            elif uptodate is False:
                utd_icon, utd_fg = ClickTheme.status_icons["error"]
            else:
                utd_icon, utd_fg = ("", "")
            utd_cell = click.style(utd_icon, fg=utd_fg) if utd_fg else ""
            click.echo(f"  {name:<{_W_N}}  {status_cell}  {clone_dir:<{_W_C}}  {remote_url:<{_W_R}}  {utd_cell}")

    # --- Documents table ---
    click.echo()
    click.echo(click.style("  Documents", bold=True))
    doc_repos = eco.discover_doc_repos(root_dir, tmp_dir)
    if not doc_repos:
        click.echo(click.style("    No document repositories cloned locally.", fg="yellow"))
        return

    _CLONE_LABEL = {"root": "[JEJUNE_ROOT_DIR]", "tmp": "[.jejune/tmp]"}
    doc_rows: list[tuple[str, bool, str, bool | None]] = [
        (name, has_doc, _CLONE_LABEL.get(tier, tier), CompEcosystem.repo_uptodate(Path(path_str)))
        for name, tier, path_str, has_doc in doc_repos
    ]
    _ICON_W = 1  # display width of ✓/✗
    _W_DN = max(len("Repository"),      max(len(r[0]) for r in doc_rows))
    _W_DC = max(len("Clone directory"), max(len(r[2]) for r in doc_rows))
    _W_UTD = len("Up-to-date")

    click.echo(f"  {'Repository':<{_W_DN}}  {'':>{_ICON_W}}  {'Clone directory':<{_W_DC}}  Up-to-date")
    click.echo("  " + "─" * (_W_DN + 2 + _ICON_W + 2 + _W_DC + 2 + _W_UTD))
    for name, has_doc, clone_dir, uptodate in doc_rows:
        icon, fg = ClickTheme.status_icons["ok" if has_doc else "error"]
        doc_cell = click.style(icon, fg=fg)
        if uptodate is True:
            utd_icon, utd_fg = ClickTheme.status_icons["ok"]
        elif uptodate is False:
            utd_icon, utd_fg = ClickTheme.status_icons["error"]
        else:
            utd_icon, utd_fg = ("", "")
        utd_cell = click.style(utd_icon, fg=utd_fg) if utd_fg else ""
        click.echo(f"  {name:<{_W_DN}}  {doc_cell}  {clone_dir:<{_W_DC}}  {utd_cell}")


@ecosystem.command("update")
@click.pass_context
def ecosystem_update(ctx) -> None:
    """Fetch and reset all repos cloned in .jejune/tmp to their remote HEAD."""
    app = ctx.find_object(AppContext)
    eco = app.component_registry.get("ecosystem")
    results = eco.update_all_tmp_repos()
    if not results:
        click.echo("No repositories found in .jejune/tmp/.")
        return
    for name, was_updated in results:
        status = click.style("updated", fg="green") if was_updated else "already up-to-date"
        click.echo(f"  {name}: {status}")
