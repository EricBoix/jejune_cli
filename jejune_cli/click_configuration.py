import click

from .configuration import configuration


def print_config_check(config: configuration) -> None:
    """Print detailed per-variable config check for a component's configuration."""
    if not config:
        click.echo(click.style("no configuration required", fg="green"))
        return
    entries = config.entries_check()
    col_width = max(len(env_var) for env_var, _ in entries)
    any_error = False
    for env_var, status in entries:
        if status == "missing":
            label = click.style("not set", fg="yellow")
        elif status == "placeholder":
            label = click.style("placeholder", fg="red")
            any_error = True
        else:
            label = click.style("ok", fg="green")
        click.echo(f"  {env_var:<{col_width}}  {label}")
    if any_error:
        raise SystemExit(1)


def print_config_hint(config: configuration) -> None:
    """Print the configuration hint for a component."""
    if not config:
        click.echo(click.style("no configuration required", fg="green"))
        return
    hints = config.hints()
    click.echo(", ".join(hints) if hints else click.style("no configuration required", fg="green"))


def print_config_status(config: configuration) -> None:
    """Print configuration status for a component; exit 1 on error."""
    if not config:
        click.echo(click.style("configured", fg="green"))
        return
    status, _, hint = config.check()
    if status == "ok":
        click.echo(click.style("configured", fg="green"))
    elif status == "warn":
        click.echo(f"{click.style('not configured', fg='yellow')}  {hint}")
    else:
        click.echo(f"{click.style('error', fg='red')}  {hint}")
        raise SystemExit(1)
