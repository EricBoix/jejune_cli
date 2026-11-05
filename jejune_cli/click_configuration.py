import click

from .configuration import Configuration


def print_config_check(config: Configuration, exit_on_not_set: bool = False) -> None:
    """Print detailed per-variable config check for a component's configuration.

    Each failing variable is followed by the file to edit. A placeholder value
    or a value rejected by the entry's validator always exits 1; an unset
    variable exits 1 only when exit_on_not_set is true.
    """
    if not config:
        click.echo(click.style("no configuration required", fg="green"))
        return
    col_width = max(len(entry.env_var) for entry in config.entries)
    any_error = False
    for entry in config.entries:
        separator = "  "
        env_var = entry.env_var
        status, message = entry.check()
        if message == "missing":
            label = click.style("not set", fg="yellow")
            any_error = any_error or exit_on_not_set
        elif message == "placeholder":
            label = click.style("placeholder", fg="red")
            any_error = True
        elif status != "ok":
            # Validator failure: the message explains what is wrong with the value
            label = click.style(message or status, fg="red")
            separator = "; "
            any_error = True
        else:
            click.echo(f"  {env_var:<{col_width}}  {click.style('ok', fg='green')}")
            continue
        if entry.source_file:
            edit_hint = f"{separator}edit {entry.source_file}"
        elif entry.hint:
            edit_hint = f"{separator}{entry.hint}"
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
