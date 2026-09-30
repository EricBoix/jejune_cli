"""Next-step command group and heuristic registrations."""
import click

from .app_context import AppContext
from .dot_jejune import dot_jejune


@click.group("next", invoke_without_command=True, short_help="Show suggested next actions given the current context.")
@click.pass_context
def next_cmd(ctx):
    """Show suggested next actions given the current context."""
    if ctx.invoked_subcommand is not None:
        return
    app = ctx.find_object(AppContext)
    steps = app.heuristic_step_registry.evaluate()
    if not steps:
        if app.heuristic_step_registry.command_viable("jejune doctor"):
            click.echo("No next steps detected. Run `jejune doctor` for system status.")
        else:
            active_role = app.role_registry.detect_role()
            if (not active_role or active_role.is_doc_steward()) and not dot_jejune().is_dir():
                click.echo(
                    "No next steps detected. "
                    "Run `jejune configuration doc-steward init` to set up the workspace."
                )
            else:
                click.echo("No next steps detected.")
        return
    click.echo("Suggested next steps:")
    for step in steps:
        cmd = step.resolved_command()
        suffix = f"  →  {cmd}" if cmd else ""
        click.echo(f"  • {step.label}{suffix}")


@next_cmd.command("state")
@click.option("--list-preconditions", is_flag=True, default=False,
              help="List all registered preconditions with their current status.")
@click.pass_context
def next_state_cmd(ctx, list_preconditions: bool) -> None:
    """Show condition evaluation for all registered heuristic rules."""
    app = ctx.find_object(AppContext)
    named_preconditions = app.heuristic_step_registry.named_preconditions
    command_preconditions = app.heuristic_step_registry.command_preconditions

    if list_preconditions:
        if named_preconditions:
            click.echo("Preconditions:")
            _W = max(len(n) for n in named_preconditions)
            for name in sorted(named_preconditions):
                try:
                    val = named_preconditions[name]()
                except Exception:
                    val = False
                mark = click.style("✓", fg="green") if val else click.style("✗", fg="red")
                click.echo(f"  {mark} {name:<{_W}}")

        if command_preconditions:
            if named_preconditions:
                click.echo()
            click.echo("Command preconditions:")
            _W = max(len(cmd) for cmd in command_preconditions)
            for cmd in sorted(command_preconditions):
                try:
                    viable = command_preconditions[cmd]()
                except Exception:
                    viable = False
                mark = click.style("viable", fg="green") if viable else click.style("blocked", fg="red")
                click.echo(f"  {cmd:<{_W}}  {mark}")

        if not named_preconditions and not command_preconditions:
            click.echo("No preconditions registered.")
        return

    entries = app.heuristic_step_registry.evaluate_state()
    if not entries:
        click.echo("No heuristic rules registered.")
        return
    for step, cond_results, anti_results in entries:
        active = all(v for _, v in cond_results) and not any(v for _, v in anti_results)
        mark = click.style("✓", fg="green") if active else click.style("✗", fg="red")
        cmd = step.resolved_command()
        cmd_hint = f"  ({cmd})" if cmd else ""
        click.echo(f"  {mark} {step.label}{cmd_hint}  [order {step.order}]")
        for name, val in cond_results:
            cmark = click.style("✓", fg="green") if val else click.style("✗", fg="red")
            click.echo(f"       {cmark} {name}")
        for name, val in anti_results:
            amark = click.style("✓", fg="red") if val else click.style("✗", fg="green")
            suffix = "  (blocking)" if val else "  (not blocking)"
            click.echo(f"       anti: {amark} {name}{suffix}")
        click.echo()
