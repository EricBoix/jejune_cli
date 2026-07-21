import os
import subprocess
import urllib.error
import urllib.request

import click

from .configuration import component_config_check, print_config_hint, print_config_status

_CONTAINER = "jj_llm_observability"
_IMAGE     = "jaegertracing/all-in-one"
_OTLP_PORT = 4318
_UI_PORT   = 16686


def container_running() -> tuple[bool, str]:
    """Return (is_running, message) for the LLM observability container."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", _CONTAINER],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        return False, "not started"
    return True, "ok"


@click.group("llm-observability", short_help="Manage the LLM observability backend")
def llm_observability():
    """Manage the LLM observability backend (OTLP trace receiver)."""


@llm_observability.command("check-config")
def check_config():
    """Check whether the llm-observability component is properly configured."""
    print_config_status("llm-observability")


@llm_observability.command("hint-config")
def hint_config():
    """Show the configuration hint for the llm-observability component."""
    print_config_hint("llm-observability")


@llm_observability.command("start")
@click.option("--otlp-port", default=_OTLP_PORT, show_default=True,
              help="OTLP HTTP receiver port (must match TRACELOOP_BASE_URL).")
@click.option("--ui-port",   default=_UI_PORT,   show_default=True,
              help="Jaeger UI port.")
def start(otlp_port, ui_port):
    """Start the LLM observability Docker container (Jaeger all-in-one).

    Receives OTLP traces from `graph extract` via TRACELOOP_BASE_URL.
    """
    click.echo(f"Starting {_CONTAINER} ...")
    result = subprocess.run([
        "docker", "run", "--rm", "--detach",
        "--name", _CONTAINER,
        "--publish", f"{otlp_port}:{_OTLP_PORT}",
        "--publish", f"{ui_port}:{_UI_PORT}",
        _IMAGE,
    ])
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
    subprocess.run(["docker", "rm",   _CONTAINER], stderr=subprocess.DEVNULL)
    click.echo("LLM observability stopped.")


@llm_observability.command("status")
def status():
    """Report the LLM observability container state and endpoint reachability."""
    cfg_status, hint = component_config_check("llm-observability")
    if cfg_status != "ok":
        click.echo(f"  {click.style('not configured', fg='yellow')}  {hint}")
        return

    running, _ = container_running()
    url = os.environ.get("TRACELOOP_BASE_URL", f"http://localhost:{_OTLP_PORT}")

    if running:
        container_text = click.style("running",    fg="green")
    else:
        container_text = click.style("not running", fg="yellow")
    click.echo(f"  container   {container_text}")

    try:
        with urllib.request.urlopen(url, timeout=5):
            reachable = True
    except urllib.error.HTTPError:
        reachable = True   # server responded — endpoint is up
    except urllib.error.URLError:
        reachable = False

    if reachable:
        endpoint_text = click.style("reachable",   fg="green")
    elif running:
        endpoint_text = click.style("unreachable", fg="red")
    else:
        endpoint_text = click.style("unreachable", fg="yellow")
    click.echo(f"  endpoint    {endpoint_text}  ({url})")
