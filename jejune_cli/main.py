import click

from ._env import dot_jejune, load_env_files
from .catalog import catalog, run_all
from .deployment import deployment
from .env import env
from .graph import graph
from .neo4j import neo4j
from .pdf_to_markdown import pdf_to_markdown

_W_NAME = 22   # "catalog:test-inference" = 22
_W_MSG  = 16   # "not configured" = 14
_W_CMD  = 28   # "neo4j, graph dump-turtle" = 25

# Command → checks that must pass for the command to be usable.
_COMMAND_CHECKS: list[tuple[str, list[str]]] = [
    ("neo4j, graph dump-turtle",  ["env:neo4j"]),
    ("graph extract",             ["env:neo4j", "env:llm", "catalog:test-inference"]),
    ("pdf-to-markdown test",      ["env:workspace", "catalog:check"]),
    ("catalog check",             ["env:workspace", "catalog:check"]),
]

_STATUS_RANK  = {"error": 2, "warn": 1, "ok": 0}
_STATUS_LABEL = {"ok": "ok", "warn": "not configured", "error": "error"}

# Per-check remediation hints shown in the summary when a check fails.
_CHECK_HINTS: dict[str, str] = {
    "env:neo4j":     "edit .jejune/env-secrets",
    "env:llm":       "edit .jejune/env-secrets",
    "env:workspace": "edit .jejune/env-secrets",
    "catalog:check":          "run `jejune catalog check`",
    "catalog:test-inference": "check LLM server connectivity",
}


def _command_status(check_names: list[str], by_name: dict[str, str]) -> str:
    """Return the worst status among the named checks."""
    return max(
        (by_name.get(n, "ok") for n in check_names),
        key=lambda s: _STATUS_RANK.get(s, 0),
    )


def _row_width(col1_width: int, col3_text: str) -> int:
    """Visual width: indent(2) + col1 + space + status(_W_MSG) + space + col3."""
    return 2 + col1_width + 1 + _W_MSG + 1 + len(col3_text)


@click.group()
def cli():
    """jejune — jejuneness workflow CLI.

    Single-document commands (operate on one jj_doc_* repository):\n
      jejune env      Manage the local .jejune/ environment\n
      jejune neo4j    Manage the Neo4j instance\n
      jejune graph    Build and export the knowledge graph\n

    Collection-level commands (operate across a catalog of repositories):\n
      jejune catalog        Manage the document catalog\n
      jejune deployment     Manage deployments\n
      jejune pdf-to-markdown  Test the pipeline across the catalog\n

    Run `jejune env init` first in a repository, then `jejune doctor`.
    """
    load_env_files()


@cli.command()
def doctor():
    """Run all workspace coherence checks and report overall health.

    Equivalent to running every `jejune env check` and `jejune catalog check`
    in sequence. Inspired by `brew doctor`.
    """
    d = dot_jejune()
    if not d.is_dir():
        click.echo(click.style(
            f"No .jejune/ directory found in {d.parent}.\n"
            "Run `jejune env init` first to set up the workspace.",
            fg="yellow",
        ))
        raise SystemExit(1)

    results = run_all()
    by_name    = {name: status  for name, status, _, _   in results}
    by_message = {name: message for name, _,      message, _ in results}
    failed: list[str] = []

    # Pre-compute command rows (failing/passing split) so widths are known.
    cmd_rows: list[tuple[str, str, list[str], list[str]]] = [
        (
            cmd,
            _command_status(check_names, by_name),
            [n for n in check_names if by_name.get(n, "ok") != "ok"],
            [n for n in check_names if by_name.get(n, "ok") == "ok"],
        )
        for cmd, check_names in _COMMAND_CHECKS
    ]

    # Separator width = widest row across both tables.
    sep = max(
        _row_width(_W_NAME, "Needed by"),
        _row_width(_W_CMD,  "Checks"),
        *(_row_width(_W_NAME, usage)            for *_, usage in results),
        *(_row_width(_W_CMD,  ", ".join(f + p)) for _, _, f, p in cmd_rows),
    )

    # ── Check table ──────────────────────────────────────────────────
    click.echo("jejune doctor")
    click.echo("=" * sep)
    click.echo("  Config: .jejune/env-config (non-secret defaults) · .jejune/env-secrets (credentials)")
    click.echo()
    click.echo(f"  {'Check':<{_W_NAME}} {'Status':<{_W_MSG}} Needed by")
    click.echo("  " + "─" * (sep - 2))

    for name, status, _, usage in results:
        label_text = _STATUS_LABEL[status]
        if status == "ok":
            label = click.style(f"{label_text:<{_W_MSG}}", fg="green")
        elif status == "warn":
            label = click.style(f"{label_text:<{_W_MSG}}", fg="yellow")
        else:
            label = click.style(f"{label_text:<{_W_MSG}}", fg="red")
            failed.append(name)
        click.echo(f"  {name:<{_W_NAME}} {label} {usage}")

    # ── Command table ────────────────────────────────────────────────
    click.echo()
    click.echo(f"  {'Command':<{_W_CMD}} {'Status':<{_W_MSG}} Checks")
    click.echo("  " + "─" * (sep - 2))

    for cmd, status, failing, passing in cmd_rows:
        label_text = _STATUS_LABEL[status]
        colored_checks = ", ".join(
            [click.style(n, fg="red")   for n in failing] +
            [click.style(n, fg="green") for n in passing]
        )
        if status == "ok":
            label = click.style(f"{label_text:<{_W_MSG}}", fg="green")
        elif status == "warn":
            label = click.style(f"{label_text:<{_W_MSG}}", fg="yellow")
        else:
            label = click.style(f"{label_text:<{_W_MSG}}", fg="red")
        click.echo(f"  {cmd:<{_W_CMD}} {label} {colored_checks}")

    # ── Summary ──────────────────────────────────────────────────────
    click.echo("=" * sep)
    if not failed:
        click.echo(click.style("Your jejune workspace looks healthy.", fg="green"))
    else:
        click.echo(click.style("Some checks failed:", fg="red"))
        click.echo()
        _W_HINT_NAME = max(len(n) for n in failed)
        _W_HINT_ACT  = max(len(_CHECK_HINTS.get(n, "investigate")) for n in failed)
        for name in failed:
            action  = _CHECK_HINTS.get(name, "investigate")
            detail  = by_message[name]
            colored = click.style(f"{name:<{_W_HINT_NAME}}", fg="red")
            click.echo(f"  {colored}  {action:<{_W_HINT_ACT}}  [{detail}]")


cli.add_command(env)
cli.add_command(neo4j)
cli.add_command(graph)
cli.add_command(catalog)
cli.add_command(deployment)
cli.add_command(pdf_to_markdown)
cli.add_command(doctor)
