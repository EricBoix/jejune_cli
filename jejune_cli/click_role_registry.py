"""Role command groups for the jejune CLI."""

import textwrap
import click

from .app_context import AppContext
from .role_descriptions import role_description

_WRAP_WIDTH = 78


def _build_inheritance_line(
    role_name: str,
    includes: tuple[str, ...],
    abstract_roles: set[str],
) -> str:
    """Return a formatted inheritance line, or '' if the role has no parents."""
    if not includes:
        return ""
    desc = role_description(role_name)
    role_title = desc.title if desc else role_name
    formatted: list[str] = []
    for parent_name in includes:
        tag = " (abstract)" if parent_name in abstract_roles else ""
        formatted.append(f"{parent_name}{tag}")
    if len(formatted) == 1:
        parents_str = formatted[0]
    elif len(formatted) == 2:
        parents_str = f"{formatted[0]} and {formatted[1]}"
    else:
        parents_str = ", ".join(formatted[:-1]) + f", and {formatted[-1]}"
    return f"Inheritance: {role_title} role inherits from {parents_str}."


def _display_role_section(
    role_name: str,
    title_suffix: str = "",
    show_title: bool = True,
    inheritance_line: str = "",
    indent: str = "",
) -> None:
    """Print the project description for *role_name* to stdout."""
    desc = role_description(role_name)
    if desc is None:
        click.echo(f"{indent}(no project description for role '{role_name}')")
        return
    if show_title:
        click.echo(click.style(f"{desc.title}{title_suffix}", bold=True))
    click.echo()
    click.echo(
        textwrap.fill(
            desc.general_description,
            width=_WRAP_WIDTH,
            initial_indent=indent,
            subsequent_indent=indent,
        )
    )
    click.echo()
    click.echo(f"{indent}Responsibilities:")
    for responsibility in desc.responsibilities:
        click.echo(
            textwrap.fill(
                responsibility,
                width=_WRAP_WIDTH,
                initial_indent=f"{indent}  - ",
                subsequent_indent=f"{indent}    ",
            )
        )
    if inheritance_line:
        click.echo()
        click.echo(f"{indent}{inheritance_line}")


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


@role.command("describe")
@click.pass_context
def role_describe(ctx):
    """Show the project description for the currently detected role."""
    app = ctx.find_object(AppContext)
    active_role = app.role_registry.detect_role()
    if not active_role:
        click.echo(click.style("No role detected in current directory.", fg="yellow"))
        return
    abstract = app.role_registry.abstract_roles
    inheritance_line = _build_inheritance_line(
        active_role.name, active_role.includes, abstract
    )
    _display_role_section(
        active_role.name,
        title_suffix=" role description",
        inheritance_line=inheritance_line,
    )


@click.group(short_help="List or describe roles")
def roles():
    """List, inspect hierarchy, or describe roles."""


@roles.command("list")
@click.pass_context
def roles_list(ctx):
    """List all known roles with their detection mode."""
    app = ctx.find_object(AppContext)
    active = app.role_registry.detect_role()
    abstract = app.role_registry.abstract_roles
    rows: list[tuple[bool, str, str, str]] = []
    for role_name in app.role_registry.roles:
        role_obj = app.role_registry._roles[role_name]
        display = f"{role_name} (abstract)" if role_name in abstract else role_name
        detection = (
            "auto-detected" if role_obj.detector is not None else "inherited only"
        )
        rows.append(
            (
                role_obj is active,
                display,
                app.role_registry.description(role_name),
                detection,
            )
        )

    w_name = max(len(row[1]) for row in rows)
    w_desc = max(len(row[2]) for row in rows)
    w_det = max(len(row[3]) for row in rows)
    click.echo(
        f"  {'':2}{'Role':<{w_name}}  {'Description':<{w_desc}}  {'Detection':<{w_det}}"
    )
    click.echo(f"  {'':2}{'-' * w_name}  {'-' * w_desc}  {'-' * w_det}")
    for is_active, display, description, detection in rows:
        mark = click.style("✓", fg="green") + " " if is_active else "  "
        click.echo(f"  {mark}{display:<{w_name}}  {description:<{w_desc}}  {detection}")


@roles.command("hierarchy")
@click.pass_context
def roles_hierarchy(ctx):
    """Display the role inheritance hierarchy as a UML inheritance diagram."""
    app = ctx.find_object(AppContext)
    for line in app.role_registry.build_hierarchy_lines():
        click.echo(line)


@roles.command("describe")
@click.pass_context
def roles_describe(ctx):
    """List all roles and show their project description for each."""
    app = ctx.find_object(AppContext)
    active = app.role_registry.detect_role()
    abstract = app.role_registry.abstract_roles
    for role_name in app.role_registry.roles:
        role_obj = app.role_registry._roles[role_name]
        if role_name in abstract:
            continue
        if role_description(role_name) is None:
            continue
        is_active = role_obj is active
        desc = role_description(role_name)
        active_mark = " " + click.style("✓", fg="green") if is_active else ""
        click.echo(click.style(desc.title, bold=True) + active_mark)
        inheritance_line = _build_inheritance_line(
            role_name, role_obj.includes, abstract
        )
        _display_role_section(
            role_name, show_title=False, inheritance_line=inheritance_line, indent="  "
        )
        click.echo()
