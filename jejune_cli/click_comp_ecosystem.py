"""The `jejune ecosystem` command group."""

import click
from pathlib import Path

from .app_context import AppContext
from .component_catalog_file import CatalogFile
from .click_theme import ClickTheme
from .component_ecosystem import CompEcosystem
from .dot_jejune import DotJejune


class _StatusTable:
    """What the tables of `ecosystem status` share: the placeholders standing for
    the directories listed in the header, and the Up-to-date / Commit cells."""

    LOCATION_LABEL = {"root": "[JEJUNE_ROOT_DIR]", "tmp": "[ECOSYSTEM_DIR]"}
    REPO_ROOT_LABEL = "[REPO_ROOT_DIR]"
    ICON_WIDTH = 1  # display width of ✓/✗
    UP_TO_DATE_HEADER = "Up-to-date"
    UP_TO_DATE_PAD = (len(UP_TO_DATE_HEADER) - 1) // 2
    COMMIT_HEADER = "Commit"

    @staticmethod
    def remote_label(remote_url: str, repo_root_dir: str) -> str:
        """*remote_url* with its REPO_ROOT_DIR prefix replaced by its placeholder."""
        if remote_url.startswith(repo_root_dir):
            return _StatusTable.REPO_ROOT_LABEL + remote_url[len(repo_root_dir) :]
        return remote_url

    @staticmethod
    def up_to_date_cell(up_to_date: bool | None) -> str:
        """The centred, padded Up-to-date cell."""
        if up_to_date is None:
            icon, color = "", ""
        else:
            icon, color = ClickTheme.status_icons["ok" if up_to_date else "error"]
        cell = click.style(icon, fg=color) if color else ""
        pad = _StatusTable.UP_TO_DATE_PAD
        trail = len(_StatusTable.UP_TO_DATE_HEADER) - pad - _StatusTable.ICON_WIDTH
        # Unstyled blanks of the icon width when there is no icon
        icon_blank = "" if cell else " " * _StatusTable.ICON_WIDTH
        return f"{'':>{pad}}{cell}{icon_blank}{'':<{trail}}"

    @staticmethod
    def icon_cell(ok: bool, icon_header: str) -> str:
        """The ✓/✗ cell, centred under *icon_header*."""
        icon, color = ClickTheme.status_icons["ok" if ok else "error"]
        pad = (len(icon_header) - _StatusTable.ICON_WIDTH) // 2
        trail = len(icon_header) - pad - _StatusTable.ICON_WIDTH
        return f"{'':>{pad}}{click.style(icon, fg=color)}{'':<{trail}}"

    @staticmethod
    def header(
        first, icon_header, location_header, first_width, location_width
    ) -> str:
        """The header row: *first* is bold and *location_header* is centred."""
        bold_first = click.style(f"{first:<{first_width}}", bold=True)
        return (
            f"  {bold_first}  {icon_header}  "
            f"{location_header:^{location_width}}  "
            f"{_StatusTable.UP_TO_DATE_HEADER}  {_StatusTable.COMMIT_HEADER}"
        )

    @staticmethod
    def rule(first_width, icon_header, location_width, commit_width) -> str:
        total = (
            first_width
            + 2
            + len(icon_header)
            + 2
            + location_width
            + 2
            + len(_StatusTable.UP_TO_DATE_HEADER)
            + 2
            + commit_width
        )
        return "  " + "─" * total


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
    directories = eco.resolve_dirs()
    root_dir = directories.root_dir

    role_label = f"  [{role.name}]" if role else ""
    click.echo(f"jejune ecosystem{role_label}")
    click.echo()

    # --- Environment header ---
    _W = 15  # width of label column

    root_val = str(root_dir) if root_dir else click.style("<UNSET>", fg="red")
    click.echo(f"  {'JEJUNE_ROOT_DIR':<{_W}}  {root_val}")

    repo_root_dir = app.component_registry.get("git-server").repo_root_dir()
    click.echo(f"  {'REPO_ROOT_DIR':<{_W}}  {repo_root_dir}")
    click.echo(f"  {'ECOSYSTEM_DIR':<{_W}}  {DotJejune.TMP_RELATIVE_PATH}")
    click.echo()

    # --- Components table ---
    active = app.role_registry.role_components(role)
    # Repositories needed by the active components, plus those registered with the
    # ecosystem on their behalf. The remote of those not cloned is probed: reachable
    # or not is what their icon tells.
    states = eco.repository_states(
        (
            []
            if active is None
            else [comp for comp in app.component_registry if comp in active]
        ),
        directories,
    )
    if not states:
        click.echo(
            click.style(
                "    No repositories required for the current role.", fg="yellow"
            )
        )
    else:
        rows: list[tuple[str, bool, str, bool | None, str]] = []
        for state in states:
            if state.location.is_local:
                location = _StatusTable.LOCATION_LABEL[state.location.tier]
            else:
                location = _StatusTable.remote_label(state.remote_url, repo_root_dir)
            rows.append(
                (
                    state.name,
                    state.is_available,
                    location,
                    state.up_to_date,
                    state.commit or "",
                )
            )

        _W_N = max(len("Component"), max(len(r[0]) for r in rows))
        _W_R = max(len("Repository"), max(len(r[2]) for r in rows))
        _W_COMMIT = max(len(_StatusTable.COMMIT_HEADER), max(len(r[4]) for r in rows))

        click.echo(
            _StatusTable.header("Component", "Available", "Repository", _W_N, _W_R)
        )
        click.echo(_StatusTable.rule(_W_N, "Available", _W_R, _W_COMMIT))
        for name, found, location, up_to_date, commit in rows:
            click.echo(
                f"  {name:<{_W_N}}  {_StatusTable.icon_cell(found, 'Available')}  "
                f"{location:<{_W_R}}  "
                f"{_StatusTable.up_to_date_cell(up_to_date)}  {commit}"
            )

    # --- Documents table ---
    click.echo()
    doc_repos = eco.discover_doc_repos(directories)
    known_names = {name for name, _, _, _ in doc_repos}
    if not doc_repos:
        click.echo(
            click.style("    No document repositories cloned locally.", fg="yellow")
        )
        _echo_catalog_entries_unknown_to_ecosystem(eco, known_names)
        return

    # Private catalog entries are reached with their own access key, as `update` does
    catalog_path = CatalogFile.resolve_path()
    token_files = (
        CatalogFile(catalog_path).token_files() if catalog_path.is_file() else {}
    )
    doc_rows: list[tuple[str, bool, str, bool | None, str]] = [
        (
            name,
            has_doc,
            _StatusTable.LOCATION_LABEL.get(tier, tier),
            eco.repo_up_to_date(Path(path_str), token_files.get(name)),
            eco.short_head(Path(path_str)) or "",
        )
        for name, tier, path_str, has_doc in doc_repos
    ]
    _W_DN = max(len("Document"), max(len(r[0]) for r in doc_rows))
    _W_DC = max(len("Repository"), max(len(r[2]) for r in doc_rows))
    _W_DCOMMIT = max(len(_StatusTable.COMMIT_HEADER), max(len(r[4]) for r in doc_rows))

    click.echo(_StatusTable.header("Document", "Manifest", "Repository", _W_DN, _W_DC))
    click.echo(_StatusTable.rule(_W_DN, "Manifest", _W_DC, _W_DCOMMIT))
    for name, has_doc, location, up_to_date, commit in doc_rows:
        click.echo(
            f"  {name:<{_W_DN}}  {_StatusTable.icon_cell(has_doc, 'Manifest')}  "
            f"{location:<{_W_DC}}  "
            f"{_StatusTable.up_to_date_cell(up_to_date)}  {commit}"
        )
    _echo_catalog_entries_unknown_to_ecosystem(eco, known_names)


def _echo_catalog_entries_unknown_to_ecosystem(
    eco: CompEcosystem, known_names: set[str]
) -> None:
    """List the catalog entries that are neither in JEJUNE_ROOT_DIR nor in .jejune/tmp."""
    catalog_path = CatalogFile.resolve_path()
    click.echo()
    click.echo(click.style("  Catalog", bold=True))
    if not catalog_path.is_file():
        click.echo(click.style(f"    No catalog at {catalog_path}.", fg="yellow"))
        return
    try:
        entry_names = CatalogFile(catalog_path).names()
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
    catalog = app.component_registry.get("catalog")
    catalog_path = CatalogFile.resolve_path()
    if not catalog_path.is_file():
        click.echo(
            click.style(
                f"No catalog at {catalog_path}: only updating .jejune/tmp/.",
                fg="yellow",
            )
        )
    outcomes = catalog.updater.update_all_repos(catalog_path)
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
