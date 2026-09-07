import os
import urllib.error
import urllib.request

import click

from .component_registry import REGISTRY as COMP_REGISTRY
from .click_comp_configuration import (
    print_config_check,
    print_config_hint,
    print_config_status,
)

llm_obs_comp = COMP_REGISTRY.get("llm-observability")


def llm_observability_available() -> tuple[bool, str]:
    """Config-guard + container check; consumed by catalog.run_all() and *-availability commands."""
    cfg_status, *_ = llm_obs_comp.configuration.check()
    if cfg_status != "ok":
        return False, "not configured"
    return llm_obs_comp.is_running()


@click.group("llm-observability", short_help="Manage the LLM observability backend")
def llm_observability():
    """Manage the LLM observability backend (OTLP trace receiver)."""


@llm_observability.command("check-config")
def check_config():
    """Show per-variable configuration detail for the llm-observability component."""
    print_config_check(llm_obs_comp.configuration)


@llm_observability.command("status-config")
def status_config():
    """Show llm-observability configuration status."""
    print_config_status(llm_obs_comp.configuration)


@llm_observability.command("hint-config")
def hint_config():
    """Show the configuration hint for the llm-observability component."""
    print_config_hint(llm_obs_comp.configuration)


@llm_observability.command("start")
@click.option(
    "--otlp-port",
    default=llm_obs_comp.otlp_port,
    show_default=True,
    help="OTLP HTTP receiver port (must match TRACELOOP_BASE_URL).",
)
@click.option("--ui-port", default=llm_obs_comp.ui_port, show_default=True, help="Jaeger UI port.")
def start(otlp_port, ui_port):
    """Start the LLM observability Docker container (Jaeger all-in-one).

    Receives OTLP traces from `graph extract` via TRACELOOP_BASE_URL.
    """
    import subprocess
    click.echo(f"Starting {llm_obs_comp.container_name} ...")
    result = subprocess.run([
        "docker", "run", "--rm", "--detach",
        "--name", llm_obs_comp.container_name,
        "--publish", f"{otlp_port}:{llm_obs_comp.otlp_port}",
        "--publish", f"{ui_port}:{llm_obs_comp.ui_port}",
        llm_obs_comp.image_name,
    ])
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    click.echo(f"  OTLP receiver : http://localhost:{otlp_port}")
    click.echo(f"  Jaeger UI     : http://localhost:{ui_port}")


@llm_observability.command("stop")
def stop():
    """Stop and remove the LLM observability Docker container."""
    llm_obs_comp.stop()


@llm_observability.command("check-availability")
def check_availability():
    """Show detailed llm-observability availability (container state and endpoint reachability)."""
    ok, msg = llm_observability_available()
    if msg == "not configured":
        click.echo(f"  {click.style('not configured', fg='yellow')}  {llm_obs_comp.configuration.hint}")
        return
    running = ok
    url = os.environ.get("TRACELOOP_BASE_URL", f"http://localhost:{llm_obs_comp.otlp_port}")
    try:
        with urllib.request.urlopen(url, timeout=5):
            reachable = True
    except urllib.error.HTTPError:
        reachable = True
    except urllib.error.URLError:
        reachable = False
    click.echo(
        f"  container   {click.style('running', fg='green') if running else click.style('not running', fg='yellow')}"
    )
    ep_color = "green" if reachable else ("red" if running else "yellow")
    click.echo(
        f"  endpoint    {click.style('reachable' if reachable else 'unreachable', fg=ep_color)}  ({url})"
    )


@llm_observability.command("status-availability")
def status_availability():
    """Show llm-observability availability status."""
    ok, msg = llm_observability_available()
    if ok:
        click.echo(f"llm-observability: {click.style('ok', fg='green')}")
    elif msg == "not configured":
        click.echo(f"llm-observability: {click.style('not configured', fg='yellow')}")
    else:
        click.echo(f"llm-observability: {click.style(msg, fg='yellow')}")


@llm_observability.command("hint-availability")
def hint_availability():
    """Show how to start llm-observability if it is not running."""
    ok, msg = llm_observability_available()
    if ok:
        click.echo(click.style("llm-observability is running", fg="green"))
    elif msg == "not configured":
        click.echo(llm_obs_comp.configuration.hint)
    else:
        click.echo("run `jejune llm-observability start`")
