import json
import os
import urllib.error
import urllib.request

import click

from .configuration import print_config_hint, print_config_status

_TEST_PROMPT = "How are you today?"
_TIMEOUT = 10            # seconds — used for all checks except inference
_INFERENCE_TIMEOUT = 120 # seconds — large models can be slow to respond
DEFAULT_INFERENCE_PATH = "/api/chat"


def infer_server_url(model_url: str) -> str:
    """Derive the OpenWebUI root URL from the Ollama base URL.

    OpenWebUI proxies Ollama at <root>/ollama, so the server root is obtained
    by stripping the /ollama suffix when present.  For a bare Ollama instance
    (no proxy) the two URLs are identical.

    Examples:
        https://host/ollama  →  https://host
        https://host         →  https://host
    """
    stripped = model_url.rstrip("/")
    if stripped.endswith("/ollama"):
        return stripped[: -len("/ollama")]
    return stripped


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
        with urllib.request.urlopen(req, timeout=_INFERENCE_TIMEOUT) as resp:
            resp.read()
        return True, "ok"
    except urllib.error.HTTPError as e:
        return False, f"inference failed: {e.code} {e.reason}"
    except urllib.error.URLError as e:
        return False, f"inference failed: {e.reason}"
    except TimeoutError:
        return False, f"inference timed out after {_INFERENCE_TIMEOUT}s"


def llm_available() -> tuple[bool, str]:
    """Quick availability check: server reachable and API key valid.

    Reads LLM_MODEL_URL, LLM_API_KEY, and optionally LLM_SERVER_URL from the
    environment.  Intended as a preflight guard before launching containers.
    Returns (False, "not configured") when required env vars are absent.
    """
    url     = (os.environ.get("LLM_MODEL_URL") or "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY") or ""
    if not url or not api_key:
        return False, "not configured"
    explicit = os.environ.get("LLM_SERVER_URL")
    server_url = explicit.rstrip("/") if explicit else infer_server_url(url)
    passed, msg = check_server(server_url)
    if not passed:
        return False, msg
    return check_auth(server_url, api_key)


def _llm_check_context() -> tuple[str, str, str, str, str] | None:
    """Resolve check parameters from env vars; return None when not fully configured."""
    url = (os.environ.get("LLM_MODEL_URL") or "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY") or ""
    model = os.environ.get("LLM_MODEL_NAME") or ""
    if not url or not api_key or not model:
        return None
    explicit = os.environ.get("LLM_SERVER_URL")
    server_url = explicit.rstrip("/") if explicit else infer_server_url(url)
    inference_path = os.environ.get("LLM_INFERENCE_ENDPOINT", DEFAULT_INFERENCE_PATH)
    return url, api_key, model, server_url, inference_path


def llm_check_availability() -> tuple[bool, str]:
    """Full 5-step availability check; consumed by catalog.run_all() and *-availability commands."""
    ctx = _llm_check_context()
    if ctx is None:
        return False, "not configured"
    url, api_key, model, server_url, inference_path = ctx
    for fn in (
        lambda: check_server(server_url),
        lambda: check_auth(server_url, api_key),
        lambda: check_model(server_url, api_key, model),
        lambda: check_inference_endpoint(url, api_key, inference_path),
        lambda: check_inference(url, api_key, model, inference_path),
    ):
        passed, msg = fn()
        if not passed:
            return False, msg
    return True, "ok"


@click.group(short_help="Manage the LLM inference server")
def llm():
    """Manage the LLM inference server."""


@llm.command("check-config")
def check_config():
    """Show per-variable configuration detail for the llm component."""
    from .configuration import print_config_check
    print_config_check("llm")


@llm.command("status-config")
def status_config():
    """Show llm configuration status."""
    print_config_status("llm")


@llm.command("hint-config")
def hint_config():
    """Show the configuration hint for the llm component."""
    print_config_hint("llm")




@llm.command("check-availability")
@click.option("--prompt", default=_TEST_PROMPT, show_default=True,
              help="Prompt sent to the LLM for the inference round-trip test.")
def check_availability(prompt):
    """Show detailed llm availability (five-stage connectivity and inference check)."""
    ctx = _llm_check_context()
    if ctx is None:
        missing = [n for n in ("LLM_MODEL_URL", "LLM_API_KEY", "LLM_MODEL_NAME")
                   if not os.environ.get(n)]
        raise click.ClickException(f"Missing: {', '.join(missing)}")
    url, api_key, model, server_url, inference_path = ctx
    steps = [
        ("HTTPS connectivity",    lambda: check_server(server_url)),
        ("API key",               lambda: check_auth(server_url, api_key)),
        ("Model exists",          lambda: check_model(server_url, api_key, model)),
        ("Inference endpoint",    lambda: check_inference_endpoint(url, api_key, inference_path)),
        ("Inference round-trip",  lambda: check_inference(url, api_key, model, inference_path, prompt)),
    ]
    for i, (label, fn) in enumerate(steps, 1):
        click.echo(f"  [{i}/{len(steps)}] {label}... ", nl=False)
        passed, msg = fn()
        click.echo(click.style("ok", fg="green") if passed else click.style(f"FAILED — {msg}", fg="red"))
        if not passed:
            raise SystemExit(1)


@llm.command("status-availability")
def status_availability():
    """Show llm availability status."""
    ok, msg = llm_check_availability()
    if ok:
        click.echo(f"llm: {click.style('ok', fg='green')}")
    elif msg == "not configured":
        click.echo(f"llm: {click.style('not configured', fg='yellow')}")
    else:
        click.echo(f"llm: {click.style('error', fg='red')}")


@llm.command("hint-availability")
def hint_availability():
    """Show how to fix the first failing LLM availability stage."""
    ctx = _llm_check_context()
    if ctx is None:
        click.echo("edit .jejune/env-secrets: set LLM_MODEL_URL, LLM_API_KEY, LLM_MODEL_NAME")
        return
    url, api_key, model, server_url, inference_path = ctx
    stages = [
        (lambda: check_server(server_url),
         "verify LLM_MODEL_URL / LLM_SERVER_URL is reachable from this host"),
        (lambda: check_auth(server_url, api_key),
         "verify LLM_API_KEY in .jejune/env-secrets"),
        (lambda: check_model(server_url, api_key, model),
         "verify LLM_MODEL_NAME matches a model available on the server"),
        (lambda: check_inference_endpoint(url, api_key, inference_path),
         "verify LLM_INFERENCE_ENDPOINT (default /api/chat)"),
        (lambda: check_inference(url, api_key, model, inference_path),
         "check LLM server logs or try a different model"),
    ]
    for fn, hint in stages:
        passed, _ = fn()
        if not passed:
            click.echo(hint)
            return
    click.echo(click.style("all LLM checks pass", fg="green"))
