import json
import os
import urllib.error
import urllib.request

import click

from .configuration import print_config_hint, print_config_status

_TEST_PROMPT = "How are you today?"
_TIMEOUT = 10  # seconds
DEFAULT_INFERENCE_PATH = "/api/chat/completions"


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


def check_model(url: str, api_key: str, model: str) -> tuple[bool, str]:
    """Stage 3: does the model exist on the server? (GET /api/models)."""
    auth = {"Authorization": f"BEARER {api_key}"}
    req = urllib.request.Request(f"{url}/api/models", headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        return False, f"model list unavailable: {e.reason}"
    except json.JSONDecodeError:
        return False, "model list: unexpected response format"

    models = [m.get("id", "") for m in data.get("data", [])]
    if model in models:
        return True, "ok"
    if models:
        shown = ", ".join(models[:5])
        suffix = f" … ({len(models)} total)" if len(models) > 5 else ""
        hint = f"available: {shown}{suffix}"
    else:
        hint = "no models returned"
    return False, f"model {model!r} not found — {hint}"


def check_inference_endpoint(url: str, api_key: str, path: str) -> tuple[bool, str]:
    """Stage 4: does the inference endpoint accept POST? (empty body to probe the path)."""
    auth = {"Authorization": f"BEARER {api_key}"}
    req = urllib.request.Request(
        f"{url}{path}",
        data=b"{}",
        headers={**auth, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        return True, "ok"
    except urllib.error.HTTPError as e:
        if e.code in (400, 422):
            return True, "ok"  # endpoint exists; bad-request is expected for an empty body
        return False, f"endpoint error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"endpoint unreachable: {e.reason}"


def check_inference(
    url: str, api_key: str, model: str, path: str, prompt: str = _TEST_PROMPT
) -> tuple[bool, str]:
    """Stage 5: does inference succeed? Uses OpenAI-compatible request body."""
    auth = {"Authorization": f"BEARER {api_key}"}
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{url}{path}",
        data=payload,
        headers={**auth, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        return True, "ok"
    except urllib.error.HTTPError as e:
        return False, f"inference failed: {e.code} {e.reason}"
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
    Optionally reads LLM_INFERENCE_ENDPOINT (default: /api/chat/completions).
    Performs five checks:\n
      1. GET  <LLM_MODEL_URL>                        — HTTPS-level reachability\n
      2. GET  <LLM_MODEL_URL>/api/v1/auths/          — API key valid\n
      3. GET  <LLM_MODEL_URL>/api/models             — configured model exists on server\n
      4. POST <LLM_MODEL_URL><LLM_INFERENCE_ENDPOINT> — inference endpoint accepts POST\n
      5. POST <LLM_MODEL_URL><LLM_INFERENCE_ENDPOINT> — inference round-trip succeeds\n
    """
    url            = os.environ.get("LLM_MODEL_URL")
    api_key        = os.environ.get("LLM_API_KEY")
    model          = os.environ.get("LLM_MODEL_NAME")
    inference_path = os.environ.get("LLM_INFERENCE_ENDPOINT", DEFAULT_INFERENCE_PATH)

    missing = [n for n, v in [
        ("LLM_MODEL_URL", url), ("LLM_API_KEY", api_key), ("LLM_MODEL_NAME", model)
    ] if not v]
    if missing:
        raise click.ClickException(f"Missing environment variables: {', '.join(missing)}")

    click.echo(f"Server   : {url}")
    click.echo(f"Model    : {model}")
    click.echo(f"Endpoint : {inference_path}")
    click.echo(f"Prompt   : {prompt!r}")
    click.echo()

    steps = [
        ("HTTPS connectivity",       lambda: check_server(url)),
        ("API key",                   lambda: check_auth(url, api_key)),
        ("Model exists on server",    lambda: check_model(url, api_key, model)),
        ("Inference endpoint",        lambda: check_inference_endpoint(url, api_key, inference_path)),
        ("Inference round-trip",      lambda: check_inference(url, api_key, model, inference_path, prompt)),
    ]
    n = len(steps)
    for i, (label, fn) in enumerate(steps, 1):
        click.echo(f"  [{i}/{n}] {label}... ", nl=False)
        passed, msg = fn()
        if passed:
            click.echo(click.style("ok", fg="green"))
        else:
            click.echo(click.style(f"FAILED — {msg}", fg="red"))
            raise SystemExit(1)
