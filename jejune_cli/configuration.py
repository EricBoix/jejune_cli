import shutil
from pathlib import Path

import click

from ._env import dot_jejune

_TEMPLATES = Path(__file__).parent / "templates"
_PLACEHOLDER = "_CHANGE_ME"

# Config groups: name → (env vars, components that require them).
# "warn" (yellow) = none set — use case not configured, valid.
# "error" (red)   = partial or placeholder — needs attention.
CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {
    "neo4j":            (["NEO4J_PASSWORD"],                                  "neo4j, graph dump-turtle, graph extract"),
    "llm":              (["LLM_MODEL_URL", "LLM_API_KEY", "LLM_MODEL_NAME"], "graph extract"),
    "llm-observability":(["TRACELOOP_BASE_URL"],                              "graph extract (tracing)"),
    "convert":          (["CONVERT_DOC_DIR"],                                 "convert build, convert run"),
}


# Hints shown when a component's configuration is incomplete.
COMPONENT_CONFIG_HINTS: dict[str, str] = {
    "neo4j":             "edit .jejune/env-secrets or .jejune/env-config",
    "llm":               "edit .jejune/env-secrets",
    "llm-observability": "configure TRACELOOP_BASE_URL in .jejune/env-config",
    "convert":           "set CONVERT_DOC_DIR in .jejune/env-config",
}


_STATUS_DISPLAY: dict[str, tuple[str, str]] = {
    "ok":    ("ok",             "green"),
    "warn":  ("not configured", "yellow"),
    "error": ("error",          "red"),
}


def print_config_table(
    rows: list[tuple[str, str, str, str]],
    hint_header: str = "Hint",
) -> None:
    """Render Component configuration | Status | Check | <hint_header> table."""
    if not rows:
        return
    _W_C = max(len("Component configuration"), max(len(r[0]) for r in rows))
    _W_S = max(len("Status"), max(len(_STATUS_DISPLAY.get(r[1], (r[1], ""))[0]) for r in rows))
    _W_K = max(len("Check"), max(len(r[2]) for r in rows))
    _W_H = max(len(hint_header), max(len(r[3]) for r in rows))
    click.echo(f"  {'Component configuration':<{_W_C}}  {'Status':<{_W_S}}  {'Check':<{_W_K}}  {hint_header}")
    click.echo("  " + "─" * (_W_C + 2 + _W_S + 2 + _W_K + 2 + _W_H))
    for comp, status, check, hint in rows:
        text, fg = _STATUS_DISPLAY.get(status, (status, "white"))
        click.echo(f"  {comp:<{_W_C}}  {click.style(f'{text:<{_W_S}}', fg=fg)}  {check:<{_W_K}}  {hint}")


def _convert_config_status() -> tuple[str, str]:
    """Return (status, raw_msg) for convert configuration."""
    import os
    from pathlib import Path as _Path
    val = os.environ.get("CONVERT_DOC_DIR")
    if not val or _PLACEHOLDER in val:
        return "warn", "CONVERT_DOC_DIR not configured"
    p = _Path(val)
    if p.is_file():
        if not p.exists():
            return "error", f"Dockerfile not found at {p.resolve()}"
        return "ok", ""
    ctx = p / "DockerContext"
    if not ctx.is_dir():
        return "error", f"DockerContext not found at {ctx}"
    return "ok", ""


def component_config_check(component: str) -> tuple[str, str]:
    """Return (status, hint) for a component's configuration.

    For components with no required env vars the status is always "ok".
    """
    import os
    if component == "convert":
        status, msg = _convert_config_status()
        if status == "ok":
            return "ok", ""
        if status == "error":
            return status, msg  # specific: "DockerContext not found at <path>"
        return status, get_config_hint("convert", status, msg)
    if component not in CONFIG_GROUPS:
        return "ok", ""
    keys, _ = CONFIG_GROUPS[component]
    status, msg = check_config_group(keys)
    return status, get_config_hint(component, status, msg)


def get_config_hint(component: str, status: str, message: str) -> str:
    """Return the precise configuration hint given a component's status and message."""
    return COMPONENT_CONFIG_HINTS.get(component, "")


def print_config_check(component: str) -> None:
    """Print detailed per-variable config check for a component."""
    import os
    if component not in CONFIG_GROUPS:
        click.echo(click.style("no configuration required", fg="green"))
        return
    keys, _ = CONFIG_GROUPS[component]
    _W = max(len(k) for k in keys)
    any_error = False
    for key in keys:
        val = os.environ.get(key)
        if val is None:
            label = click.style("not set", fg="yellow")
        elif _PLACEHOLDER in val:
            label = click.style("placeholder", fg="red")
            any_error = True
        else:
            label = click.style("ok", fg="green")
        click.echo(f"  {key:<{_W}}  {label}")
    if any_error:
        raise SystemExit(1)


def print_config_hint(component: str) -> None:
    """Print the configuration hint for a component."""
    _, hint = component_config_check(component)
    if hint:
        click.echo(hint)
    else:
        click.echo(click.style("no configuration required", fg="green"))


def print_config_status(component: str) -> None:
    """Print configuration status for a component; exit 1 on error."""
    status, hint = component_config_check(component)
    if status == "ok":
        click.echo(click.style("configured", fg="green"))
    elif status == "warn":
        click.echo(f"{click.style('not configured', fg='yellow')}  {hint}")
    else:
        click.echo(f"{click.style('error', fg='red')}  {hint}")
        raise SystemExit(1)


def check_config_group(keys: list[str]) -> tuple[str, str]:
    """Check a group of env vars; return (status, message).

    status is "ok", "warn" (none set — use case not configured), or "error"
    (partial or placeholder values present).
    """
    import os
    states: list[tuple[str, str]] = []
    for key in keys:
        val = os.environ.get(key)
        if val is None:
            states.append((key, "missing"))
        elif _PLACEHOLDER in val:
            states.append((key, "placeholder"))
        else:
            states.append((key, "ok"))

    if all(s == "ok" for _, s in states):
        return "ok", "ok"
    if all(s == "missing" for _, s in states):
        return "warn", "not configured"
    issues = [f"{k}: {s}" for k, s in states if s != "ok"]
    return "error", "; ".join(issues)


@click.group(short_help="Manage the .jejune/ configuration")
def configuration():
    """Manage the .jejune/ configuration (env-config, env-secrets, catalog.yaml)."""


@configuration.command("init")
def init():
    """Write jejune scaffold files into .jejune/ in the current directory.

    Creates .jejune/env-config, .jejune/env-secrets, and
    .jejune/catalog.yaml from built-in templates.
    Adds .jejune to .gitignore so the whole directory stays local by default.
    """
    d = dot_jejune()
    d.mkdir(exist_ok=True)

    created = []
    skipped = []
    for fname in ("env-config", "env-secrets", "catalog.yaml"):
        dst = d / fname
        if dst.exists():
            skipped.append(fname)
        else:
            shutil.copy2(_TEMPLATES / fname, dst)
            created.append(fname)

    for f in created:
        click.echo(click.style(f"  created  .jejune/{f}", fg="green"))
    for f in skipped:
        click.echo(click.style(f"  skipped  .jejune/{f} (already exists)", fg="yellow"))

    gitignore = Path.cwd() / ".gitignore"
    entry = ".jejune\n"
    if not gitignore.exists() or ".jejune" not in gitignore.read_text().splitlines():
        with gitignore.open("a") as fh:
            fh.write(entry)
        click.echo(click.style("  updated  .gitignore (.jejune)", fg="green"))

    click.echo()
    click.echo("Next step: edit .jejune/env-secrets with your credentials.")


@configuration.command("check-config")
def check():
    """Verify configuration variables by component group.

    Reports each group (neo4j, llm) independently:\n
      ok             — all vars set and non-placeholder\n
      not configured — none set (use case not activated, not an error)\n
      error          — partial or placeholder values (needs attention)\n

    Checks os.environ, which already includes values loaded from
    .jejune/env-config and .jejune/env-secrets at startup.
    """
    from .role import detect_role, role_components
    role, _ = detect_role()
    visible = role_components(role)
    groups = {g: v for g, v in CONFIG_GROUPS.items() if visible is None or g in visible}

    if not groups:
        click.echo(click.style("no configuration required for the current role", fg="green"))
        return

    rows = [
        (group, status, msg if status == "error" else "", COMPONENT_CONFIG_HINTS.get(group, "") if status != "ok" else "")
        for group, (keys, _) in groups.items()
        for status, msg in [check_config_group(keys)]
    ]
    print_config_table(rows)
    if any(status == "error" for _, status, _, _ in rows):
        raise SystemExit(1)


configuration.add_command(check, "summary")


def _role_groups() -> dict:
    """Return CONFIG_GROUPS filtered to the currently detected role."""
    from .role import detect_role, role_components
    role, _ = detect_role()
    visible = role_components(role)
    return {g: v for g, v in CONFIG_GROUPS.items() if visible is None or g in visible}


@configuration.command("status-config")
def configuration_status():
    """Per-component configuration status (Component | Status)."""
    groups = _role_groups()
    if not groups:
        click.echo(click.style("no configuration required for the current role", fg="green"))
        return
    rows = [(group, check_config_group(keys)[0]) for group, (keys, _) in groups.items()]
    _W_C = max(len("Component configuration"), max(len(r[0]) for r in rows))
    _W_S = max(len("Status"), max(len(_STATUS_DISPLAY.get(r[1], (r[1], ""))[0]) for r in rows))
    click.echo(f"  {'Component configuration':<{_W_C}}  Status")
    click.echo("  " + "─" * (_W_C + 2 + _W_S))
    for comp, st in rows:
        text, fg = _STATUS_DISPLAY.get(st, (st, "white"))
        click.echo(f"  {comp:<{_W_C}}  {click.style(text, fg=fg)}")


@configuration.command("hint-config")
def configuration_hint():
    """Configuration hints for non-ok components (Component | Hint)."""
    groups = _role_groups()
    items = [(group, check_config_group(keys)[0]) for group, (keys, _) in groups.items()]
    rows = [(comp, COMPONENT_CONFIG_HINTS.get(comp, "")) for comp, status in items if status != "ok"]
    rows = [(c, h) for c, h in rows if h]
    if not rows:
        click.echo(click.style("all components configured", fg="green"))
        return
    _W_C = max(len("Component configuration"), max(len(r[0]) for r in rows))
    _W_H = max(len("Hint"), max(len(r[1]) for r in rows))
    click.echo(f"  {'Component configuration':<{_W_C}}  Hint")
    click.echo("  " + "─" * (_W_C + 2 + _W_H))
    for comp, hint in rows:
        click.echo(f"  {comp:<{_W_C}}  {hint}")
