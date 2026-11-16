"""Discover command — static navigation hints for the CLI."""

import click


@click.command("discover", short_help="Show discovery hints for navigating the CLI.")
def discover_cmd() -> None:
    """Show discovery hints for navigating the CLI."""
    click.echo(
        "  • Commands to try (when lost)  →  jejune doctor, components, roles, plugin-packages..."
    )
    click.echo("  • Discover all available jejune commands  →  jejune --help")
