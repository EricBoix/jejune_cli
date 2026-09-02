"""Aggregate health-check used by ``jejune doctor``."""

from .convert import convert_configured as _convert_configured, image_built as _convert_image_built
from .neo4j import container_running as _neo4j_running
from .ecosystem import ecosystem_needs_remote as _ecosystem_needs_remote

# Maps doctor component names to docker-compose service names for the UI trio.
# Must stay in sync with ui_deployment._UI_SERVICES.
_UI_COMP_SERVICES: dict[str, str] = {
    "docs-server": "docs-server",
    "kg-viewer":   "kg-graph-viewer",
    "md-browser":  "markdown-browser",
}


def _validate_ui_comp_services() -> None:
    """Assert that _UI_COMP_SERVICES keys are known component names.

    Lazy import of _BASE_COMPONENTS required: _doctor.py imports run_all from
    this module at its own module level, so a top-level import here would be
    circular.
    """
    from ._doctor import _BASE_COMPONENTS
    _base = frozenset(_BASE_COMPONENTS)
    unknown = set(_UI_COMP_SERVICES) - _base
    assert not unknown, f"_UI_COMP_SERVICES keys contain unknown component names: {unknown}"


def run_all(
    components: set[str] | None = None,
) -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
]:
    """Return (config_results, avail_results) for jejune doctor.

    Each entry is (component, status, message).
    When *components* is given, only those components are checked.
    """
    _validate_ui_comp_services()
    from .configuration import CONFIG_GROUPS, check_config_group
    from .plugin import _REGISTRY

    config: list[tuple[str, str, str]] = []
    avail:  list[tuple[str, str, str]] = []

    def _visible(name: str) -> bool:
        return components is None or name in components

    for group, group_def in CONFIG_GROUPS.items():
        if not _visible(group):
            continue
        keys = group_def[0]
        max_severity = group_def[2] if len(group_def) > 2 else "error"
        status, msg = check_config_group(keys)
        if max_severity == "warn" and status == "error":
            status = "warn"
        config.append((group, status, msg))

    if _visible("docker-command"):
        from .docker_command import is_docker_command_available as _check_docker
        config.append(("docker-command", "ok", ""))
        ok = _check_docker()
        avail.append(("docker-command", "ok" if ok else "error", "" if ok else "docker not found on PATH"))

    if _visible("neo4j"):
        from .configuration import component_config_check
        cfg_status, _ = component_config_check("neo4j")
        running, msg = _neo4j_running()
        if running:
            status = "ok"
        elif cfg_status != "ok":
            status = "warn"
        else:
            status = "error"
        avail.append(("neo4j", status, msg))

    if _visible("llm"):
        from .llm import llm_check_availability as _llm_check
        ok, msg = _llm_check()
        status = "ok" if ok else ("warn" if msg == "not configured" else "error")
        avail.append(("llm", status, msg))

    if _visible("llm-observability"):
        from .llm_observability import llm_observability_available as _lo_available
        ok, msg = _lo_available()
        avail.append(("llm-observability", "ok" if ok else "warn", msg))

    if _visible("graph"):
        from .graph import graph_available as _graph_available
        ok, msg = _graph_available()
        avail.append(("graph", "ok" if ok else "error", msg))

    if _visible("convert") and _convert_configured():
        built, msg = _convert_image_built()
        avail.append(("convert", "ok" if built else "warn", msg))

    if _visible("manifest"):
        from pathlib import Path
        from .test import _manifest_avail_status, _manifest_config_status
        cfg_status, cfg_msg = _manifest_config_status(Path.cwd())
        config.append(("manifest", cfg_status, cfg_msg))
        avail_status, avail_msg = _manifest_avail_status(Path.cwd())
        if cfg_status == "error" and avail_status == "ok":
            avail_status, avail_msg = cfg_status, cfg_msg
        avail.append(("manifest", avail_status, avail_msg))

    if _visible("network") or _visible("git-command") or _visible("git-repos-access"):
        _remote = _ecosystem_needs_remote()
    else:
        _remote = False

    if _visible("network") and _remote:
        from .network import is_network_available as _is_network_available
        ok = _is_network_available()
        avail.append(("network", "ok" if ok else "error",
                      "" if ok else "GitHub not reachable"))

    if _visible("docker-hub-server"):
        from .docker_hub_server import check_docker_hub_server
        ok, msg = check_docker_hub_server()
        avail.append(("docker-hub-server", "ok" if ok else "error", msg))

    if _visible("pypi-server"):
        from .pypi_server import check_pypi_server as _check_pypi_server
        ok, msg = _check_pypi_server()
        avail.append(("pypi-server", "ok" if ok else "error", msg))

    if _visible("git-command") and _remote:
        from .git_command import is_git_command_available as _is_git_command_available
        ok = _is_git_command_available()
        avail.append(("git-command", "ok" if ok else "error",
                      "" if ok else "git not found on PATH"))

    if _visible("uv-command"):
        from .uv_command import is_uv_command_available as _is_uv_command_available
        ok = _is_uv_command_available()
        avail.append(("uv-command", "ok" if ok else "error",
                      "" if ok else "uv not found on PATH"))

    if _visible("extensions"):
        from .deployer_extensions import _extensions_installed
        ok = _extensions_installed()
        avail.append(("extensions", "ok" if ok else "error", "" if ok else "not installed"))

    _plugin_names = {p.name for p in _REGISTRY}
    for ui_comp, svc_name in _UI_COMP_SERVICES.items():
        if not _visible(ui_comp) or ui_comp in _plugin_names:
            continue
        from pathlib import Path
        from . import containers as _c
        deploy_name = Path(".").resolve().name.lower()
        ok = _c.is_running(f"jejune-{deploy_name}-{svc_name}-1")
        avail.append((ui_comp, "ok" if ok else "error", "" if ok else "container not running"))

    for plugin in _REGISTRY:
        if not _visible(plugin.name):
            continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return config, avail
