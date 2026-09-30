import subprocess

import click

from .app_context import AppContext
from .click_configuration import (
    print_config_check,
    print_config_hint,
    print_config_status,
)


@click.group("llm-observability", short_help="Manage the LLM observability backend")
@click.pass_context
def llm_observability(ctx):
    """Manage the LLM observability backend (OTLP trace receiver)."""
    ctx.obj = ctx.find_object(AppContext).component_registry.get("llm-observability")


@llm_observability.command("check-config")
@click.pass_obj
def check_config(comp):
    """Show per-variable configuration detail for the llm-observability component."""
    print_config_check(comp.configuration)


@llm_observability.command("status-config")
@click.pass_obj
def status_config(comp):
    """Show llm-observability configuration status."""
    print_config_status(comp.configuration)


@llm_observability.command("hint-config")
@click.pass_obj
def hint_config(comp):
    """Show the configuration hint for the llm-observability component."""
    print_config_hint(comp.configuration)


@llm_observability.command("start")
@click.option(
    "--otlp-port",
    default=None,
    help="OTLP HTTP receiver port (must match TRACELOOP_BASE_URL).",
)
@click.option("--ui-port", default=None, help="Jaeger UI port.")
@click.pass_obj
def start(comp, otlp_port, ui_port):
    """Start the LLM observability Docker container (Jaeger all-in-one).

    Receives OTLP traces from `graph extract` via TRACELOOP_BASE_URL.
    """
    if otlp_port is None:
        otlp_port = comp.otlp_port
    if ui_port is None:
        ui_port = comp.ui_port
    click.echo(f"Starting {comp.container_name} ...")
    result = subprocess.run([
        "docker", "run", "--rm", "--detach",
        "--name", comp.container_name,
        "--publish", f"{otlp_port}:{comp.otlp_port}",
        "--publish", f"{ui_port}:{comp.ui_port}",
        comp.image_name,
    ])
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    click.echo(f"  OTLP receiver : http://localhost:{otlp_port}")
    click.echo(f"  Jaeger UI     : http://localhost:{ui_port}")


@llm_observability.command("stop")
@click.pass_obj
def stop(comp):
    """Stop and remove the LLM observability Docker container."""
    comp.stop()


@llm_observability.command("check-availability")
@click.pass_obj
def check_availability(comp):
    """Show detailed llm-observability availability (container state and endpoint reachability)."""
    ok, msg = comp.available()
    if msg == "not configured":
        hints = ", ".join(comp.configuration.hints())
        click.echo(f"  {click.style('not configured', fg='yellow')}  {hints}")
        return
    reachable, url = comp.check_endpoint_reachable()
    click.echo(
        f"  container   {click.style('running', fg='green') if ok else click.style('not running', fg='yellow')}"
    )
    ep_color = "green" if reachable else ("red" if ok else "yellow")
    click.echo(
        f"  endpoint    {click.style('reachable' if reachable else 'unreachable', fg=ep_color)}  ({url})"
    )


@llm_observability.command("status-availability")
@click.pass_obj
def status_availability(comp):
    """Show llm-observability availability status."""
    ok, msg = comp.available()
    if ok:
        click.echo(f"llm-observability: {click.style('ok', fg='green')}")
    elif msg == "not configured":
        click.echo(f"llm-observability: {click.style('not configured', fg='yellow')}")
    else:
        click.echo(f"llm-observability: {click.style(msg, fg='yellow')}")


@llm_observability.command("hint-availability")
@click.pass_obj
def hint_availability(comp):
    """Show how to start llm-observability if it is not running."""
    ok, msg = comp.available()
    if ok:
        click.echo(click.style("llm-observability is running", fg="green"))
    elif msg == "not configured":
        click.echo(", ".join(comp.configuration.hints()))
    else:
        click.echo("run `jejune llm-observability start`")
