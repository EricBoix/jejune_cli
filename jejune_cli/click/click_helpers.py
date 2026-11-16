import click


def print_two_col_table(rows: list[tuple[str, str]], col1: str, col2: str) -> None:
    """Render a two-column table; rows may contain pre-styled strings."""
    _W_C = max(len(col1), max(len(click.unstyle(row[0])) for row in rows))
    _W_V = max(len(col2), max(len(click.unstyle(row[1])) for row in rows))
    click.echo(f"  {col1:<{_W_C}}  {col2}")
    click.echo("  " + "─" * (_W_C + 2 + _W_V))
    for first_cell, second_cell in rows:
        pad = " " * (_W_C - len(click.unstyle(first_cell)))
        click.echo(f"  {first_cell}{pad}  {second_cell}")
