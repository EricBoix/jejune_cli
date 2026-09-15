import os

import click

from .component_registry import REGISTRY as COMP_REGISTRY
from .click_comp_configuration import print_config_hint, print_config_status, print_config_check


@click.group(short_help="Manage the LLM inference server")
def llm():
    """Manage the LLM inference server."""


@llm.command("check-config")
def check_config():
    """Show per-variable configuration detail for the llm component."""
    print_config_check(COMP_REGISTRY.get("llm").configuration)


@llm.command("status-config")
def status_config():
    """Show llm configuration status."""
    print_config_status(COMP_REGISTRY.get("llm").configuration)


@llm.command("hint-config")
def hint_config():
    """Show the configuration hint for the llm component."""
    print_config_hint(COMP_REGISTRY.get("llm").configuration)


@llm.command("check-availability")
@click.option("--prompt", default=None, show_default=True,
              help="Prompt sent to the LLM for the inference round-trip test.")
def check_availability(prompt):
    """Show detailed llm availability (five-stage connectivity and inference check)."""
    comp = COMP_REGISTRY.get("llm")
    ctx = comp._check_context()
    if ctx is None:
        missing = [n for n in ("LLM_MODEL_URL", "LLM_API_KEY", "LLM_MODEL_NAME")
                   if not os.environ.get(n)]
        raise click.ClickException(f"Missing: {', '.join(missing)}")
    url, api_key, model, server_url, inference_path = ctx
    effective_prompt = prompt if prompt is not None else comp._TEST_PROMPT
    steps = [
        ("HTTPS connectivity",    lambda: comp.check_server(server_url)),
        ("API key",               lambda: comp.check_auth(server_url, api_key)),
        ("Model exists",          lambda: comp.check_model(server_url, api_key, model)),
        ("Inference endpoint",    lambda: comp.check_inference_endpoint(url, api_key, inference_path)),
        ("Inference round-trip",  lambda: comp.check_inference(url, api_key, model, inference_path, effective_prompt)),
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
    ok, msg = COMP_REGISTRY.get("llm").check_availability()
    if ok:
        click.echo(f"llm: {click.style('ok', fg='green')}")
    elif msg == "not configured":
        click.echo(f"llm: {click.style('not configured', fg='yellow')}")
    else:
        click.echo(f"llm: {click.style('error', fg='red')}")


@llm.command("hint-availability")
def hint_availability():
    """Show how to fix the first failing LLM availability stage."""
    comp = COMP_REGISTRY.get("llm")
    ctx = comp._check_context()
    if ctx is None:
        click.echo("edit .jejune/env-secrets: set LLM_MODEL_URL, LLM_API_KEY, LLM_MODEL_NAME")
        return
    url, api_key, model, server_url, inference_path = ctx
    stages = [
        (lambda: comp.check_server(server_url),
         "verify LLM_MODEL_URL / LLM_SERVER_URL is reachable from this host"),
        (lambda: comp.check_auth(server_url, api_key),
         "verify LLM_API_KEY in .jejune/env-secrets"),
        (lambda: comp.check_model(server_url, api_key, model),
         "verify LLM_MODEL_NAME matches a model available on the server"),
        (lambda: comp.check_inference_endpoint(url, api_key, inference_path),
         "verify LLM_INFERENCE_ENDPOINT (default /api/chat)"),
        (lambda: comp.check_inference(url, api_key, model, inference_path),
         "check LLM server logs or try a different model"),
    ]
    for fn, hint in stages:
        passed, _ = fn()
        if not passed:
            click.echo(hint)
            return
    click.echo(click.style("all LLM checks pass", fg="green"))
