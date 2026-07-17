import click

from .build import build
from .configure import configure, run_all as configure_run_all
from .deploy import deploy
from .env import dot_jejune, load_env_files


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
    click.echo("=" * 40)

    results = configure_run_all()
    any_error = False

    for name, status, message in results:
        if status == "ok":
            label = click.style("ok", fg="green")
        elif status == "warn":
            label = click.style(message, fg="yellow")
        else:
            label = click.style(message, fg="red")
            any_error = True
        click.echo(f"  {name:<30} {label}")

    click.echo("=" * 40)
    if not any_error:
        click.echo(click.style("Your jejune workspace looks healthy.", fg="green"))
    else:
        click.echo(click.style("Some checks failed. See above.", fg="red"))


cli.add_command(configure)
cli.add_command(build)
cli.add_command(deploy)
