import click

from .build import build
from .configure import configure, run_all as configure_run_all
from .deploy import deploy
from .env import load_env_files


@click.group()
def cli():
    """jejune — jejuneness workflow CLI.

    Three command groups address the three stages of the workflow:\n
      jejune configure   Stage 1: verify workspace coherence\n
      jejune build       Stage 2: run the treatment pipeline\n
      jejune deploy      Stage 3: manage and launch deployments\n

    Run `jejune doctor` first on a fresh checkout or after any config change.
    """
    load_env_files()


@cli.command()
def doctor():
    """Run all workspace coherence checks and report overall health.

    Equivalent to running every `jejune configure` check in sequence.
    Inspired by `brew doctor`.
    """
    click.echo("jejune doctor")
    click.echo("=" * 40)

    results = configure_run_all()
    all_passed = True

    for name, passed, message in results:
        if passed:
            status = click.style("ok", fg="green")
        else:
            status = click.style(message, fg="yellow")
            all_passed = False
        click.echo(f"  {name:<30} {status}")

    click.echo("=" * 40)
    if all_passed:
        click.echo(click.style("Your jejune workspace looks healthy.", fg="green"))
    else:
        click.echo(
            click.style("Some checks are pending or failed. See above.", fg="yellow")
        )


cli.add_command(configure)
cli.add_command(build)
cli.add_command(deploy)
