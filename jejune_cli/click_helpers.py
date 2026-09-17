import click


def print_two_col_table(rows: list[tuple[str, str]], col1: str, col2: str) -> None:
    """Render a two-column table; rows may contain pre-styled strings."""
    _W_C = max(len(col1), max(len(click.unstyle(r[0])) for r in rows))
    _W_V = max(len(col2), max(len(click.unstyle(r[1])) for r in rows))
    click.echo(f"  {col1:<{_W_C}}  {col2}")
    click.echo("  " + "─" * (_W_C + 2 + _W_V))
    for c, v in rows:
        pad = " " * (_W_C - len(click.unstyle(c)))
        click.echo(f"  {c}{pad}  {v}")
