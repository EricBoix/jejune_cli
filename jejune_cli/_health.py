"""Aggregate health-check used by ``jejune doctor``."""

from .convert import convert_configured as _convert_configured, image_built as _convert_image_built
from .neo4j import container_running as _neo4j_running
from .ecosystem import ecosystem_needs_remote as _ecosystem_needs_remote


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

    if _visible("docker"):
        from .ecosystem import check_docker as _check_docker
        config.append(("docker", "ok", ""))
        ok = _check_docker()
        avail.append(("docker", "ok" if ok else "error", "" if ok else "docker not found on PATH"))

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
        from .network import check_network as _check_network
        ok = _check_network()
        avail.append(("network", "ok" if ok else "error",
                      "" if ok else "GitHub not reachable"))

    if _visible("dockerhub"):
        from .dockerhub import check_dockerhub as _check_dockerhub
        ok, msg = _check_dockerhub()
        avail.append(("dockerhub", "ok" if ok else "error", msg))

    if _visible("pypi"):
        from .pypi import check_pypi as _check_pypi
        ok, msg = _check_pypi()
        avail.append(("pypi", "ok" if ok else "error", msg))

    if _visible("git-command") and _remote:
        from .git_command import check_git as _check_git
        ok = _check_git()
        avail.append(("git-command", "ok" if ok else "error",
                      "" if ok else "git not found on PATH"))

    if _visible("extensions"):
        from .deployer_extensions import _extensions_installed
        ok = _extensions_installed()
        avail.append(("extensions", "ok" if ok else "error", "" if ok else "not installed"))

    for plugin in _REGISTRY:
        if not _visible(plugin.name):
            continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return config, avail
