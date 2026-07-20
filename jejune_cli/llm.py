import json
import os
import urllib.error
import urllib.request

import click

from .configuration import print_config_hint, print_config_status

_TEST_PROMPT = "How are you today?"
_TIMEOUT = 10  # seconds


def check_reachability(url: str, api_key: str) -> tuple[bool, str]:
    """Coarse check: is the LLM server reachable? (GET /api/tags only)."""
    auth = {"Authorization": f"BEARER {api_key}"}
    req = urllib.request.Request(f"{url}/api/tags", headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        return True, "ok"
    except urllib.error.URLError as e:
        return False, f"server unreachable: {e.reason}"



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
@click.option(
    "--prompt",
    default=_TEST_PROMPT,
    show_default=True,
    help="Prompt sent to the LLM for the inference round-trip test.",
)
def status(prompt):
    """Test LLM server connectivity and inference capability.

    Reads LLM_MODEL_URL, LLM_API_KEY, LLM_MODEL_NAME from the environment.
    Performs two checks:\n
      1. GET  <LLM_MODEL_URL>/api/tags        — server reachable and authenticated\n
      2. POST <LLM_MODEL_URL>/api/generate    — inference round-trip succeeds\n
    """
    url     = os.environ.get("LLM_MODEL_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model   = os.environ.get("LLM_MODEL_NAME")

    missing = [n for n, v in [
        ("LLM_MODEL_URL", url), ("LLM_API_KEY", api_key), ("LLM_MODEL_NAME", model)
    ] if not v]
    if missing:
        raise click.ClickException(f"Missing environment variables: {', '.join(missing)}")

    click.echo(f"Server : {url}")
    click.echo(f"Model  : {model}")
    click.echo(f"Prompt : {prompt!r}")
    click.echo()

    auth = {"Authorization": f"BEARER {api_key}"}

    click.echo("  [1/2] Server reachability... ", nl=False)
    req = urllib.request.Request(f"{url}/api/tags", headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        click.echo(click.style("ok", fg="green"))
    except urllib.error.URLError as e:
        click.echo(click.style(f"FAILED — {e.reason}", fg="red"))
        raise SystemExit(1)

    click.echo("  [2/2] Inference round-trip... ", nl=False)
    payload = json.dumps({"model": model, "prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=payload,
        headers={**auth, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        click.echo(click.style("ok", fg="green"))
    except urllib.error.URLError as e:
        click.echo(click.style(f"FAILED — {e.reason}", fg="red"))
        raise SystemExit(1)
