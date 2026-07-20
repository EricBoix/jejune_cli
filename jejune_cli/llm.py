import json
import os
import urllib.error
import urllib.request

import click

from .configuration import component_config_check, print_config_hint, print_config_status

_TEST_PROMPT = "How are you today?"
_TIMEOUT = 10  # seconds


def check_connectivity(url: str, api_key: str, model: str) -> tuple[bool, str]:
    """Test LLM server reachability and inference round-trip; return (ok, message)."""
    auth = {"Authorization": f"BEARER {api_key}"}

    req = urllib.request.Request(f"{url}/api/tags", headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
    except urllib.error.URLError as e:
        return False, f"server unreachable: {e.reason}"

    payload = json.dumps({"model": model, "prompt": _TEST_PROMPT}).encode()
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=payload,
        headers={**auth, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
    except urllib.error.URLError as e:
        return False, f"inference failed: {e.reason}"

    return True, "ok"


@click.group()
def llm():
    """Manage the LLM inference server."""


@llm.command("check-config")
def check_config():
    """Check whether the llm component is properly configured."""
    print_config_status("llm")


@llm.command("hint-config")
def hint_config():
    """Show the configuration hint for the llm component."""
    print_config_hint("llm")


@llm.command("status")
def status():
    """Report LLM server configuration and connectivity."""
    cfg_status, hint = component_config_check("llm")
    if cfg_status != "ok":
        click.echo(f"  {click.style('not configured', fg='yellow')}  {hint}")
        return

    url     = os.environ.get("LLM_MODEL_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model   = os.environ.get("LLM_MODEL_NAME")

    click.echo(f"  url         {url}")
    click.echo(f"  model       {model}")

    ok, msg = check_connectivity(url, api_key, model)
    conn_text = click.style("ok", fg="green") if ok else click.style(msg, fg="red")
    click.echo(f"  server      {conn_text}")
