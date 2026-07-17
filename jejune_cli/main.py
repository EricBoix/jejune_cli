import click

from .build import build
from .configure import configure, run_all as configure_run_all
from .deploy import deploy
from .env import dot_jejune, load_env_files
from .testing import test

_W_NAME = 16   # "check-catalog" = 13, "test-inference" = 14
_W_MSG  = 26   # truncated status message
_W_CMD  = 26   # "configure check-catalog" = 23

# Command → checks that must pass for the command to be usable.
_COMMAND_CHECKS: list[tuple[str, list[str]]] = [
    ("build neo4j-*",           ["env:neo4j"]),
    ("build kg-extract",        ["env:neo4j", "env:llm", "test-inference"]),
    ("build dump-turtle",       ["env:neo4j"]),
    ("test pdf-to-markdown",    ["env:workspace", "check-catalog"]),
    ("configure check-catalog", ["env:workspace", "check-catalog"]),
]

_STATUS_RANK  = {"error": 2, "warn": 1, "ok": 0}
_STATUS_LABEL = {"ok": "ok", "warn": "not configured", "error": "error"}


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

    Four command groups cover the workflow:\n
      jejune configure   Stage 1: verify workspace coherence\n
      jejune build       Stage 2: run the treatment pipeline\n
      jejune test        Run test suites for the pipeline\n
      jejune deploy      Stage 3: manage and launch deployments\n

    First time in a repository: run `jejune configure init` to create .jejune/.
    Then run `jejune doctor` to verify the workspace is healthy.
    """
    load_env_files()


@cli.command()
def doctor():
    """Run all workspace coherence checks and report overall health.

    Equivalent to running every `jejune configure` check in sequence.
    Inspired by `brew doctor`.
    """
    d = dot_jejune()
    if not d.is_dir():
        click.echo(click.style(
            f"No .jejune/ directory found in {d.parent}.\n"
            "Run `jejune configure init` first to set up the workspace.",
            fg="yellow",
        ))
        raise SystemExit(1)

    results = configure_run_all()
    by_name = {name: status for name, status, _, _ in results}
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
        *(_row_width(_W_NAME, usage)                    for *_, usage in results),
        *(_row_width(_W_CMD,  ", ".join(fail + ok))     for _, _, fail, ok in cmd_rows),
    )

    # ── Check table ──────────────────────────────────────────────────
    click.echo("jejune doctor")
    click.echo("=" * sep)
    click.echo(f"  {'Check':<{_W_NAME}} {'Status':<{_W_MSG}} Needed by")
    click.echo("  " + "─" * (sep - 2))

    for name, status, message, usage in results:
        snippet = message if len(message) <= _W_MSG else message[:_W_MSG - 1] + "…"
        if status == "ok":
            label = click.style(f"{snippet:<{_W_MSG}}", fg="green")
        elif status == "warn":
            label = click.style(f"{snippet:<{_W_MSG}}", fg="yellow")
        else:
            label = click.style(f"{snippet:<{_W_MSG}}", fg="red")
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
        click.echo(click.style("Some checks failed. See above.", fg="red"))
        click.echo()
        if any(n.startswith("env:") for n in failed):
            click.echo("  env:* failures    → edit .jejune/env-secrets")
        if "check-catalog" in failed:
            click.echo("  check-catalog     → run `jejune configure check-catalog` for details")
        if "test-inference" in failed:
            click.echo("  test-inference    → check LLM server connectivity"
                       " (see env:llm for credentials)")


cli.add_command(configure)
cli.add_command(build)
cli.add_command(deploy)
cli.add_command(test)
