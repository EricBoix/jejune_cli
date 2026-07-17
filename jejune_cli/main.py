import click

from .build import build
from .configure import configure, run_all as configure_run_all
from .deploy import deploy
from .env import dot_jejune, load_env_files
from .testing import test

_W_NAME = 16   # "check-catalog" = 13, "test-inference" = 14
_W_MSG  = 26   # truncated status message

# Command → checks that must pass for the command to be usable.
_COMMAND_CHECKS: list[tuple[str, list[str]]] = [
    ("build neo4j-*",           ["env:neo4j"]),
    ("build kg-extract",        ["env:neo4j", "env:llm", "test-inference"]),
    ("build dump-turtle",       ["env:neo4j"]),
    ("test pdf-to-markdown",    ["env:workspace", "check-catalog"]),
    ("configure check-catalog", ["env:workspace", "check-catalog"]),
]

_STATUS_RANK = {"error": 2, "warn": 1, "ok": 0}
_STATUS_LABEL = {"ok": "ok", "warn": "not configured", "error": "error"}


def _command_status(check_names: list[str], by_name: dict[str, str]) -> str:
    """Return the worst status among the named checks."""
    return max(
        (by_name.get(n, "ok") for n in check_names),
        key=lambda s: _STATUS_RANK.get(s, 0),
    )


@click.group()
def cli():
    """jejune — jejuneness workflow CLI.

    Three command groups address the three stages of the workflow:\n
      jejune configure   Stage 1: verify workspace coherence\n
      jejune build       Stage 2: run the treatment pipeline\n
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

    # ── Check table ─────────────────────────────────────────────────
    click.echo("jejune doctor")
    click.echo("=" * 72)
    click.echo(f"  {'Check':<{_W_NAME}} {'Status':<{_W_MSG}} Needed by")
    click.echo("  " + "─" * 68)

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
    _W_CMD = 26
    click.echo()
    click.echo(f"  {'Command':<{_W_CMD}} {'Status':<{_W_MSG}} Checks")
    click.echo("  " + "─" * 68)

    for cmd, check_names in _COMMAND_CHECKS:
        status = _command_status(check_names, by_name)
        label_text = _STATUS_LABEL[status]
        checks_str = ", ".join(check_names)
        if status == "ok":
            label = click.style(f"{label_text:<{_W_MSG}}", fg="green")
        elif status == "warn":
            label = click.style(f"{label_text:<{_W_MSG}}", fg="yellow")
        else:
            label = click.style(f"{label_text:<{_W_MSG}}", fg="red")
        click.echo(f"  {cmd:<{_W_CMD}} {label} {checks_str}")

    # ── Summary ──────────────────────────────────────────────────────
    click.echo("=" * 72)
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
