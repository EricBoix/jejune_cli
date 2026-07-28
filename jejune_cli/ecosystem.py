"""Ecosystem repository resolution and `jejune ecosystem` command group."""

import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Literal

import click

from ._ecosystem import REPO_ROOT_DIR

# ---------------------------------------------------------------------------
# Per-role repository tables
# Each entry: (repo_name, docker_context_subpath_or_None, compose_env_var_or_None)
# ---------------------------------------------------------------------------

DEPLOYER_REPOS: list[tuple[str, str | None, str | None]] = [
    ("jejune_docs_server",      "DockerContext", "DOCS_SERVER_CONTEXT"),
    ("jejune_kg-graph_viewer",  None,            "KG_GRAPH_VIEWER_CONTEXT"),
    ("jejune_markdown_browser", "DockerContext", "MARKDOWN_BROWSER_CONTEXT"),
]
CURATOR_REPOS: list[tuple[str, str | None, str | None]] = [
    ("jejune_catalog", None, None),
]
DOC_STEWARD_REPOS: list[tuple[str, str | None, str | None]] = [
    ("jejune_extract_knowledge_graph", None, None),
    ("jejune_neo4j_docker",            None, None),
    ("jejune_neo4j_to_rdf_ttl",        None, None),
]

_ROLE_REPOS: dict[str, list[tuple[str, str | None, str | None]]] = {
    "developer":       [],
    "deployer":        DEPLOYER_REPOS,
    "catalog-curator": CURATOR_REPOS,
    "doc-steward":     DOC_STEWARD_REPOS,
}

# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

RepoTier = Literal["root", "tmp", "remote"]


def repo_status(
    name: str,
    root_dir: Path | None,
    tmp_dir: Path | None,
) -> tuple[RepoTier, str]:
    """Return (tier, path_or_url) for a repo.

    Tier order: root (JEJUNE_ROOT_DIR) → tmp (.jejune/tmp) → remote URL.
    The remote URL is always the canonical GitHub URL (without subpath).
    """
    if root_dir is not None and (root_dir / name).exists():
        return "root", str(root_dir / name)
    if tmp_dir is not None and (tmp_dir / name).exists():
        return "tmp", str(tmp_dir / name)
    return "remote", f"{REPO_ROOT_DIR}/{name}"


def resolve(
    name: str,
    root_dir: Path | None,
    tmp_dir: Path | None,
    subpath: str | None = None,
) -> str:
    """Return the path or git URL to use as a Docker build context.

    For root/tmp tiers: returns absolute local path (with subpath appended if given).
    For remote tier: returns git URL with #main:<subpath> fragment when subpath given.
    """
    tier, base = repo_status(name, root_dir, tmp_dir)
    if tier in ("root", "tmp"):
        return str(Path(base) / subpath) if subpath else base
    url = f"{REPO_ROOT_DIR}/{name}.git"
    if subpath:
        url += f"#main:{subpath}"
    return url


def repos_for_role(role: str | None) -> list[tuple[str, str | None, str | None]]:
    """Return the repo list for role, including transitively included roles."""
    from .role import _ROLE_INCLUDES
    seen: set[str] = set()
    result: list[tuple[str, str | None, str | None]] = []
    roles_to_visit = [role] if role else []
    while roles_to_visit:
        r = roles_to_visit.pop(0)
        if r in seen:
            continue
        seen.add(r)
        result.extend(_ROLE_REPOS.get(r, []))
        roles_to_visit.extend(_ROLE_INCLUDES.get(r, ()))
    return result


# ---------------------------------------------------------------------------
# Availability checks (used by run_all in catalog.py)
# ---------------------------------------------------------------------------

def check_git() -> bool:
    """Return True if git is available on PATH."""
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True, check=True,
        )
        return True
    except Exception:
        return False


def check_network(url: str = REPO_ROOT_DIR, timeout: int = 5) -> bool:
    """Return True if url is reachable."""
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def check_developer_avail() -> tuple[bool, str]:
    """Check git availability and network reachability of REPO_ROOT_DIR."""
    git_ok = check_git()
    net_ok = check_network()
    if git_ok and net_ok:
        return True, "git ok, network ok"
    parts = []
    if not git_ok:
        parts.append("git not found on PATH")
    if not net_ok:
        parts.append(f"{REPO_ROOT_DIR} not reachable")
    return False, "; ".join(parts)


# ---------------------------------------------------------------------------
# `jejune ecosystem` command group
# ---------------------------------------------------------------------------

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
    from ._env import dot_jejune

    role, _ = detect_role()

    raw_root = os.environ.get("JEJUNE_ROOT_DIR")
    root_dir = Path(raw_root).resolve() if raw_root else None
    tmp_dir = dot_jejune() / "tmp"
    if not tmp_dir.is_dir():
        tmp_dir = None

    role_label = f"  [{role}]" if role else ""
    click.echo(f"jejune ecosystem{role_label}")
    click.echo()

    # --- Environment header ---
    _W = 15  # width of label column

    root_val = str(root_dir) if root_dir else click.style("(not set)", fg="yellow")
    root_ok  = root_dir is not None and root_dir.is_dir()
    root_status = click.style("set", fg="green") if root_ok else click.style("not set", fg="yellow")
    click.echo(f"  {'JEJUNE_ROOT_DIR':<{_W}}  {root_val:<50}  {root_status}")

    git_ok  = check_git()
    net_ok  = check_network()
    net_str  = click.style("reachable", fg="green") if net_ok else click.style("unreachable", fg="red")
    git_str  = click.style("git ok", fg="green") if git_ok else click.style("git missing", fg="red")
    click.echo(f"  {'REPO_ROOT_DIR':<{_W}}  {REPO_ROOT_DIR:<50}  {net_str}  {git_str}")
    click.echo()

    # --- Repository table ---
    repos = repos_for_role(role)
    if not repos:
        click.echo(click.style("  No repositories required for the current role.", fg="yellow"))
        return

    rows: list[tuple[str, str, str, str]] = []
    for name, _, _ in repos:
        tier, path = repo_status(name, root_dir, tmp_dir)
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
