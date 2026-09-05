"""The `jejune ecosystem` command group."""

import click

from .role import repos_for_role
from .component_base import base_comp
COMP_REGISTRY = base_comp.registry


@click.group(invoke_without_command=True, short_help="Ecosystem repository status")
@click.pass_context
def ecosystem(ctx: click.Context) -> None:
    """Show ecosystem repository resolution status."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(ecosystem_status)


@ecosystem.command("status")
def ecosystem_status() -> None:
    """List required repositories and their local/remote resolution status."""
    from .role import detect_role

    eco = COMP_REGISTRY.get("ecosystem")
    role, _ = detect_role()
    root_dir, tmp_dir = eco.resolve_dirs()

    role_label = f"  [{role}]" if role else ""
    click.echo(f"jejune ecosystem{role_label}")
    click.echo()

    # --- Environment header ---
    _W = 15  # width of label column

    root_val = str(root_dir) if root_dir else click.style("(not set)", fg="yellow")
    root_ok  = root_dir is not None and root_dir.is_dir()
    root_status = click.style("set", fg="green") if root_ok else click.style("not set", fg="yellow")
    click.echo(f"  {'JEJUNE_ROOT_DIR':<{_W}}  {root_val:<50}  {root_status}")

    click.echo(f"  {'REPO_ROOT_DIR':<{_W}}  {COMP_REGISTRY.get('git-server').repo_root_dir()}")
    click.echo()

    # --- Components table ---
    repos = repos_for_role(role)
    click.echo(click.style("  Components", bold=True))
    if not repos:
        click.echo(click.style("    No repositories required for the current role.", fg="yellow"))
    else:
        rows: list[tuple[str, str, str, str]] = []
        for name, _, _ in repos:
            tier, path = eco.repo_status(name, root_dir, tmp_dir)
            if tier == "root":
                clone_display, remote_display = "[JEJUNE_ROOT_DIR]", ""
            elif tier == "tmp":
                clone_display, remote_display = "[.jejune/tmp]", ""
            else:
                clone_display, remote_display = "", "[REPO_ROOT_DIR]"
            rows.append((
                name,
                "found" if tier in ("root", "tmp") else "not found",
                clone_display,
                remote_display,
            ))

        _W_N = max(len("Component"),       max(len(r[0]) for r in rows))
        _W_S = max(len("Status"),          max(len(r[1]) for r in rows))
        _W_C = max(len("Clone directory"), max(len(r[2]) for r in rows))
        _W_R = max(len("Remote repo"),     max(len(r[3]) for r in rows))
        _STATUS_FG = {"found": "green", "not found": "yellow"}

        click.echo(f"  {'Component':<{_W_N}}  {'Status':<{_W_S}}  {'Clone directory':<{_W_C}}  Remote repo")
        click.echo("  " + "─" * (_W_N + 2 + _W_S + 2 + _W_C + 2 + _W_R))
        for name, status, clone_dir, remote_url in rows:
            status_cell = click.style(f"{status:<{_W_S}}", fg=_STATUS_FG.get(status, "white"))
            click.echo(f"  {name:<{_W_N}}  {status_cell}  {clone_dir:<{_W_C}}  {remote_url}")

    # --- Documents table ---
    click.echo()
    click.echo(click.style("  Documents", bold=True))
    doc_repos = eco.discover_doc_repos(root_dir, tmp_dir)
    if not doc_repos:
        click.echo(click.style("    No document repositories cloned locally.", fg="yellow"))
        return

    _CLONE_LABEL = {"root": "[JEJUNE_ROOT_DIR]", "tmp": "[.jejune/tmp]"}
    doc_rows: list[tuple[str, bool, str]] = [
        (name, has_doc, _CLONE_LABEL.get(tier, tier))
        for name, tier, _, has_doc in doc_repos
    ]
    _W_DN = max(len("Repository"),      max(len(r[0]) for r in doc_rows))
    _W_DC = max(len("Clone directory"), max(len(r[2]) for r in doc_rows))

    click.echo(f"  {'Repository':<{_W_DN}}  manifest.yaml  Clone directory")
    click.echo("  " + "─" * (_W_DN + 2 + len("manifest.yaml") + 2 + _W_DC))
    for name, has_doc, clone_dir in doc_rows:
        doc_cell = click.style("✓", fg="green") if has_doc else click.style("✗", fg="red")
        click.echo(f"  {name:<{_W_DN}}  {doc_cell}        {clone_dir}")
