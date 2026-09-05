"""Aggregate health-check used by ``jejune doctor``."""


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
    from .component_internal import component
    from .plugin import _REGISTRY as _PLUGIN_REGISTRY
    from .component_base import base_comp
    COMP_REGISTRY = base_comp.registry

    config: list[tuple[str, str, str]] = []
    avail:  list[tuple[str, str, str]] = []

    def _visible(name: str) -> bool:
        return components is None or name in components

    # Config: all components carrying env_vars on their configuration object
    for inst in COMP_REGISTRY:
        if not hasattr(inst, 'configuration') or not inst.configuration.env_vars:
            continue
        if not _visible(inst.name):
            continue
        status, msg, _ = inst.configuration.check()
        config.append((inst.name, status, msg))

    # Avail: built-in COMP_REGISTRY components (plugins handled separately)
    _plugin_names = {p.name for p in _PLUGIN_REGISTRY}
    for inst in COMP_REGISTRY:
        if not isinstance(inst, base_comp):
            continue
        if not _visible(inst.name) or inst.name in _plugin_names:
            continue
        status, msg = inst.check()
        avail.append((inst.name, status, msg))
        if isinstance(inst, component):
            cfg = inst.check_config()
            if cfg is not None:
                config.append((inst.name, *cfg))

    # Plugin availability checks
    for plugin in _PLUGIN_REGISTRY:
        if not _visible(plugin.name):
            continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return config, avail
