import json
import os
import urllib.error
import urllib.request

import click

from .configuration import print_config_hint, print_config_status

_TEST_PROMPT = "How are you today?"
_TIMEOUT = 10  # seconds


def check_server(url: str) -> tuple[bool, str]:
    """Stage 1: does the server answer at the HTTPS level?"""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        return True, "ok"
    except urllib.error.HTTPError:
        return True, "ok"  # Any HTTP response means the server is up
    except urllib.error.URLError as e:
        return False, f"unreachable: {e.reason}"


def check_auth(url: str, api_key: str) -> tuple[bool, str]:
    """Stage 2: is the API key valid? (GET /api/v1/auths/)."""
    auth = {"Authorization": f"BEARER {api_key}"}
    req = urllib.request.Request(f"{url}/api/v1/auths/", headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        return True, "ok"
    except urllib.error.URLError as e:
        return False, f"auth failed: {e.reason}"


def check_inference(
    url: str, api_key: str, model: str, prompt: str = _TEST_PROMPT
) -> tuple[bool, str]:
    """Stage 3: does inference succeed? (POST /api/generate)."""
    auth = {"Authorization": f"BEARER {api_key}"}
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
        return True, "ok"
    except urllib.error.URLError as e:
        return False, f"inference failed: {e.reason}"


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
    Performs three checks:\n
      1. GET  <LLM_MODEL_URL>                — HTTPS-level reachability\n
      2. GET  <LLM_MODEL_URL>/api/v1/auths/  — API key valid\n
      3. POST <LLM_MODEL_URL>/api/generate   — inference round-trip succeeds\n
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

    click.echo("  [1/3] HTTPS connectivity... ", nl=False)
    passed, msg = check_server(url)
    if passed:
        click.echo(click.style("ok", fg="green"))
    else:
        click.echo(click.style(f"FAILED — {msg}", fg="red"))
        raise SystemExit(1)

    click.echo("  [2/3] API key... ", nl=False)
    passed, msg = check_auth(url, api_key)
    if passed:
        click.echo(click.style("ok", fg="green"))
    else:
        click.echo(click.style(f"FAILED — {msg}", fg="red"))
        raise SystemExit(1)

    click.echo("  [3/3] Inference round-trip... ", nl=False)
    passed, msg = check_inference(url, api_key, model, prompt)
    if passed:
        click.echo(click.style("ok", fg="green"))
    else:
        click.echo(click.style(f"FAILED — {msg}", fg="red"))
        raise SystemExit(1)
