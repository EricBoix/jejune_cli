import click

from .configuration import Configuration


def print_config_check(config: Configuration, exit_on_not_set: bool = False) -> None:
    """Print detailed per-variable config check for a component's configuration.

    Each failing variable is followed by the file to edit. A placeholder value
    always exits 1; an unset variable exits 1 only when exit_on_not_set is true.
    """
    if not config:
        click.echo(click.style("no configuration required", fg="green"))
        return
    entries = config.entries_check()
    col_width = max(len(env_var) for env_var, _ in entries)
    any_error = False
    for entry, (env_var, status) in zip(config.entries, entries):
        if status == "missing":
            label = click.style("not set", fg="yellow")
            any_error = any_error or exit_on_not_set
        elif status == "placeholder":
            label = click.style("placeholder", fg="red")
            any_error = True
        else:
            click.echo(f"  {env_var:<{col_width}}  {click.style('ok', fg='green')}")
            continue
        if entry.source_file:
            edit_hint = f"  edit {entry.source_file}"
        elif entry.hint:
            edit_hint = f"  {entry.hint}"
        else:
            edit_hint = ""
        click.echo(f"  {env_var:<{col_width}}  {label}{edit_hint}")
    if any_error:
        raise SystemExit(1)


def print_config_hint(config: Configuration) -> None:
    """Print the configuration hint for a component."""
    if not config:
        click.echo(click.style("no configuration required", fg="green"))
        return
    hints = config.hints()
    click.echo(
        ", ".join(hints)
        if hints
        else click.style("no configuration required", fg="green")
    )


def print_config_status(config: Configuration) -> None:
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
