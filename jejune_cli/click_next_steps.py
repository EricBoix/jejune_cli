"""Next-step command group and heuristic registrations."""
import click

from ._env import dot_jejune
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY


@click.group("next", invoke_without_command=True, short_help="Show suggested next actions given the current context.")
@click.pass_context
def next_cmd(ctx):
    """Show suggested next actions given the current context."""
    if ctx.invoked_subcommand is not None:
        return
    steps = HEURISTIC_STEP_REGISTRY.evaluate()
    if not steps:
        if HEURISTIC_STEP_REGISTRY.command_viable("jejune doctor"):
            click.echo("No next steps detected. Run `jejune doctor` for system status.")
        else:
            from .role_registry import ROLE_REGISTRY
            active_role = ROLE_REGISTRY.detect_role()
            if (not active_role or active_role.is_doc_steward()) and not dot_jejune().is_dir():
                click.echo(
                    "No next steps detected. "
                    "Run `jejune configuration doc-steward init` to set up the workspace."
                )
            else:
                click.echo("No next steps detected.")
        return
    click.echo("Suggested next steps:")
    for s in steps:
        cmd = s.resolved_command()
        suffix = f"  →  {cmd}" if cmd else ""
        click.echo(f"  • {s.label}{suffix}")


@next_cmd.command("state")
@click.option("--list-preconditions", is_flag=True, default=False,
              help="List all registered preconditions with their current status.")
def next_state_cmd(list_preconditions: bool) -> None:
    """Show condition evaluation for all registered heuristic rules."""
    _NAMED_PRECONDITIONS = HEURISTIC_STEP_REGISTRY.named_preconditions
    _PRECONDITIONS = HEURISTIC_STEP_REGISTRY.command_preconditions

    if list_preconditions:
        if _NAMED_PRECONDITIONS:
            click.echo("Preconditions:")
            _W = max(len(n) for n in _NAMED_PRECONDITIONS)
            for name in sorted(_NAMED_PRECONDITIONS):
                try:
                    val = _NAMED_PRECONDITIONS[name]()
                except Exception:
                    val = False
                mark = click.style("✓", fg="green") if val else click.style("✗", fg="red")
                click.echo(f"  {mark} {name:<{_W}}")

        if _PRECONDITIONS:
            if _NAMED_PRECONDITIONS:
                click.echo()
            click.echo("Command preconditions:")
            _W = max(len(cmd) for cmd in _PRECONDITIONS)
            for cmd in sorted(_PRECONDITIONS):
                try:
                    viable = _PRECONDITIONS[cmd]()
                except Exception:
                    viable = False
                mark = click.style("viable", fg="green") if viable else click.style("blocked", fg="red")
                click.echo(f"  {cmd:<{_W}}  {mark}")

        if not _NAMED_PRECONDITIONS and not _PRECONDITIONS:
            click.echo("No preconditions registered.")
        return

    entries = HEURISTIC_STEP_REGISTRY.evaluate_state()
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


