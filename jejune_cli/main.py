import click

from .build import build
from .configure import configure, run_all as configure_run_all
from .deploy import deploy
from .env import dot_jejune, load_env_files

_W_NAME = 16   # "check-catalog" = 13, "test-inference" = 14
_W_MSG  = 26   # truncated status message


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

    click.echo("jejune doctor")
    click.echo("=" * 72)
    click.echo(f"  {'Check':<{_W_NAME}} {'Status':<{_W_MSG}} Needed by")
    click.echo("  " + "─" * 68)

    results = configure_run_all()
    failed: list[str] = []

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
