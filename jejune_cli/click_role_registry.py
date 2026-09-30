"""Role command group for the jejune CLI."""
import click

from .app_context import AppContext


@click.group(invoke_without_command=True, short_help="Show or list roles")
@click.pass_context
def role(ctx):
    """Show the detected role, or use a subcommand.

    Role is inferred from the current directory. Override with JEJUNE_ROLE env var.
    """
    if ctx.invoked_subcommand is not None:
        return
    app = ctx.find_object(AppContext)
    active_role = app.role_registry.detect_role()
    role_components = app.role_registry.role_components(active_role)
    if active_role:
        click.echo(f"role:   {click.style(active_role.name, fg='cyan')}")
    else:
        click.echo(f"role:   {click.style('(none)', fg='yellow')}")
    if role_components:
        click.echo(f"shows:  {', '.join(sorted(c.name for c in role_components))}")
    else:
        click.echo("shows:  all components")


@role.command("list")
@click.pass_context
def role_list(ctx):
    """List all known roles with their detection mode."""
    app = ctx.find_object(AppContext)
    active = app.role_registry.detect_role()
    abstract = app.role_registry.abstract_roles
    rows: list[tuple[bool, str, str, str]] = []
    for role_name in app.role_registry.roles:
        role_obj = app.role_registry._roles[role_name]
        display = f"{role_name} (abstract)" if role_name in abstract else role_name
        detection = "auto-detected" if role_obj.detector is not None else "inherited only"
        rows.append((role_obj is active, display, app.role_registry.description(role_name), detection))

    w_name = max(len(row[1]) for row in rows)
    w_desc = max(len(row[2]) for row in rows)
    w_det = max(len(row[3]) for row in rows)
    click.echo(f"  {'':2}{'Role':<{w_name}}  {'Description':<{w_desc}}  {'Detection':<{w_det}}")
    click.echo(f"  {'':2}{'-' * w_name}  {'-' * w_desc}  {'-' * w_det}")
    for is_active, display, description, detection in rows:
        mark = click.style("✓", fg="green") + " " if is_active else "  "
        click.echo(f"  {mark}{display:<{w_name}}  {description:<{w_desc}}  {detection}")


@role.command("hierarchy")
@click.pass_context
def role_hierarchy(ctx):
    """Display the role inheritance hierarchy as a UML inheritance diagram."""
    app = ctx.find_object(AppContext)
    for line in app.role_registry.build_hierarchy_lines():
        click.echo(line)
