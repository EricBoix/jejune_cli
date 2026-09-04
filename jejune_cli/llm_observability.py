import os
import subprocess
import urllib.error
import urllib.request

import click

from .component_ext_server_llm_observability import llm_obs_comp
from .click_comp_configuration import (
    print_config_check,
    print_config_hint,
    print_config_status,
)

_CONTAINER = "jejune_llm_observability"
_IMAGE = "jaegertracing/all-in-one"
_OTLP_PORT = 4318
_UI_PORT = 16686


def container_running() -> tuple[bool, str]:
    """Return (is_running, message) for the LLM observability container."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", _CONTAINER],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        return False, "not started"
    return True, "ok"


def llm_observability_available() -> tuple[bool, str]:
    """Config-guard + container check; consumed by catalog.run_all() and *-availability commands."""
    cfg_status, *_ = llm_obs_comp.configuration.check()
    if cfg_status != "ok":
        return False, "not configured"
    return container_running()


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
    default=_OTLP_PORT,
    show_default=True,
    help="OTLP HTTP receiver port (must match TRACELOOP_BASE_URL).",
)
@click.option("--ui-port", default=_UI_PORT, show_default=True, help="Jaeger UI port.")
def start(otlp_port, ui_port):
    """Start the LLM observability Docker container (Jaeger all-in-one).

    Receives OTLP traces from `graph extract` via TRACELOOP_BASE_URL.
    """
    click.echo(f"Starting {_CONTAINER} ...")
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--detach",
            "--name",
            _CONTAINER,
            "--publish",
            f"{otlp_port}:{_OTLP_PORT}",
            "--publish",
            f"{ui_port}:{_UI_PORT}",
            _IMAGE,
        ]
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    click.echo(f"  OTLP receiver : http://localhost:{otlp_port}")
    click.echo(f"  Jaeger UI     : http://localhost:{ui_port}")


@llm_observability.command("stop")
def stop():
    """Stop and remove the LLM observability Docker container."""
    click.echo(f"Stopping {_CONTAINER} ...")
    subprocess.run(["docker", "stop", _CONTAINER], stderr=subprocess.DEVNULL)
    click.echo(f"Removing {_CONTAINER} ...")
    subprocess.run(["docker", "rm", _CONTAINER], stderr=subprocess.DEVNULL)
    click.echo("LLM observability stopped.")


@llm_observability.command("check-availability")
def check_availability():
    """Show detailed llm-observability availability (container state and endpoint reachability)."""
    ok, msg = llm_observability_available()
    if msg == "not configured":
        click.echo(f"  {click.style('not configured', fg='yellow')}  {llm_obs_comp.configuration.hint}")
        return
    running = ok
    url = os.environ.get("TRACELOOP_BASE_URL", f"http://localhost:{_OTLP_PORT}")
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
