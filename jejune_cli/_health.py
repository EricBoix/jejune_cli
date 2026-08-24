"""Aggregate health-check used by ``jejune doctor``."""

from .convert import convert_configured as _convert_configured, image_built as _convert_image_built
from .neo4j import container_running as _neo4j_running


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

    if _visible("neo4j"):
        running, msg = _neo4j_running()
        avail.append(("neo4j", "ok" if running else "warn", msg))

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

    if _visible("ecosystem"):
        from .ecosystem import check_contributor_avail
        ok, msg = check_contributor_avail()
        avail.append(("ecosystem", "ok" if ok else "warn", msg))

    for plugin in _REGISTRY:
        if not _visible(plugin.name):
            continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return config, avail
