"""Role command group for the jejune CLI."""
import click

from .role import ROLE_REGISTRY


@click.group(invoke_without_command=True, short_help="Show or list roles")
@click.pass_context
def role(ctx):
    """Show the detected role, or use a subcommand.

    Role is inferred from the current directory. Override with JEJUNE_ROLE env var.
    """
    if ctx.invoked_subcommand is not None:
        return
    active_role = ROLE_REGISTRY.detect_role()
    active_components = ROLE_REGISTRY.role_components(active_role)
    if active_role:
        click.echo(f"role:   {click.style(active_role.name, fg='cyan')}")
    else:
        click.echo(f"role:   {click.style('(none)', fg='yellow')}")
    if active_components:
        click.echo(f"shows:  {', '.join(sorted(active_components))}")
    else:
        click.echo("shows:  all components")


@role.command("list")
def role_list():
    """List all known roles with their detection mode."""
    active = ROLE_REGISTRY.detect_role()
    abstract = ROLE_REGISTRY.abstract_roles
    rows: list[tuple[bool, str, str, str]] = []
    for r in ROLE_REGISTRY.roles:
        role_obj = ROLE_REGISTRY._roles[r]
        display = f"{r} (abstract)" if r in abstract else r
        detection = "auto-detected" if role_obj.detector is not None else "inherited only"
        rows.append((role_obj is active, display, ROLE_REGISTRY.description(r), detection))

    w_name = max(len(row[1]) for row in rows)
    w_desc = max(len(row[2]) for row in rows)
    w_det = max(len(row[3]) for row in rows)
    click.echo(f"  {'':2}{'Role':<{w_name}}  {'Description':<{w_desc}}  {'Detection':<{w_det}}")
    click.echo(f"  {'':2}{'-' * w_name}  {'-' * w_desc}  {'-' * w_det}")
    for is_active, display, description, detection in rows:
        mark = click.style("✓", fg="green") + " " if is_active else "  "
        click.echo(f"  {mark}{display:<{w_name}}  {description:<{w_desc}}  {detection}")


@role.command("hierarchy")
def role_hierarchy():
    """Display the role inheritance hierarchy as a UML inheritance diagram."""
    for line in ROLE_REGISTRY.build_hierarchy_lines():
        click.echo(line)
