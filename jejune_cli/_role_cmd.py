"""Role command group for the jejune CLI."""
import click

from ._env import dot_jejune
from .role import _ABSTRACT_ROLES, ROLES, build_hierarchy_lines, detect_role, detect_roles, role_components


@click.group(invoke_without_command=True, short_help="Show or list roles")
@click.pass_context
def role(ctx):
    """Show the detected role, or use a subcommand.

    Role is inferred from the current directory. Override with JEJUNE_ROLE env var.
    """
    if ctx.invoked_subcommand is not None:
        return
    active_roles = detect_roles()
    _, active_role_reason = detect_role()
    active_components = role_components(active_roles)
    if active_roles:
        click.echo(f"role:   {click.style(', '.join(active_roles), fg='cyan')}")
    else:
        click.echo(f"role:   {click.style('(none)', fg='yellow')}")
    click.echo(f"reason: {active_role_reason}")
    if active_components:
        click.echo(f"shows:  {', '.join(sorted(active_components))}")
    else:
        click.echo("shows:  all components")


@role.command("list")
def role_list():
    """List all known roles with their detection mode."""
    from .role import ROLES, _ROLE_DESCRIPTION, _ROLE_REASON
    stored = None
    role_file = dot_jejune() / "role"
    if role_file.is_file():
        stored = role_file.read_text().strip().split(",")[0].strip()

    # (raw_name, display_name, description, detection)
    rows: list[tuple[str, str, str, str]] = []
    for r in ROLES:
        display = f"{r} (abstract)" if r in _ABSTRACT_ROLES else r
        description = _ROLE_DESCRIPTION.get(r, "")
        detection = _ROLE_REASON.get(r, "inherited only" if r in _ABSTRACT_ROLES else "")
        rows.append((r, display, description, detection))

    w_name = max(len(row[1]) for row in rows)
    w_desc = max(len(row[2]) for row in rows)
    w_det = max(len(row[3]) for row in rows)
    click.echo(f"  {'':2}{'Role':<{w_name}}  {'Description':<{w_desc}}  {'Detection':<{w_det}}")
    click.echo(f"  {'':2}{'-' * w_name}  {'-' * w_desc}  {'-' * w_det}")
    for raw, display, description, detection in rows:
        mark = click.style("✓", fg="green") + " " if raw == stored else "  "
        click.echo(f"  {mark}{display:<{w_name}}  {description:<{w_desc}}  {detection}")


class _SettableRole(click.ParamType):
    """Validates role names at runtime against the (plugin-extended) ROLES list."""
    name = "ROLE"

    def convert(self, value, param, ctx):
        settable = [r for r in ROLES if r not in _ABSTRACT_ROLES]
        if value not in settable:
            self.fail(
                f"'{value}' is not one of {', '.join(repr(r) for r in settable)}.",
                param, ctx,
            )
        return value


@role.command("set")
@click.argument("role_name", metavar="ROLE", type=_SettableRole())
def role_set(role_name):
    """Set the role for the current directory."""
    d = dot_jejune()
    d.mkdir(exist_ok=True)
    role_file = d / "role"
    if role_file.is_file():
        other = [p for p in d.iterdir() if p.name != "role"]
        if other:
            current = role_file.read_text().strip().split(",")[0].strip()
            click.echo(
                f"Current role ({current}) is determined by current working directory.",
                err=True,
            )
            raise SystemExit(1)
    (d / "role").write_text(f"{role_name}\n")
    click.echo(f"Role set to {click.style(role_name, fg='cyan')}.")


@role.command("hierarchy")
def role_hierarchy():
    """Display the role inheritance hierarchy as a UML inheritance diagram."""
    for line in build_hierarchy_lines():
        click.echo(line)
