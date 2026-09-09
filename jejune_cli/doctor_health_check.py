"""Aggregate health-check used by ``jejune doctor``."""

from .component_registry import REGISTRY as COMP_REGISTRY
from .component_with_config import conf_comp as component
from .plugin_registry import PLUGIN_REGISTRY
from .role_registry import ROLE_REGISTRY
import sys


def run_all() -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
]:
    """Return (config_results, avail_results) for jejune doctor.

    Each entry is (component, status, message).
    Only components relevant to the current role are checked.
    """

    config: list[tuple[str, str, str]] = []
    avail:  list[tuple[str, str, str]] = []

    # role components are always sourced in COMP_REGISTRY
    role_comps = ROLE_REGISTRY.current_role_components()
    if role_comps is None:
        print("This role has not components. How strange")
        sys.exit()

    # First display components with configured env_vars
    for inst in role_comps:
        if not isinstance(inst, component) or not inst.configuration.env_vars:
            continue
        status, msg, _ = inst.configuration.check()
        config.append((inst.name, status, msg))

    # The display built-in registry components
    plugin_component_names = {p.name for p in PLUGIN_REGISTRY.plugins}
    for inst in role_comps:
        if inst.name in plugin_component_names:
            continue
        status, msg = inst.check()
        avail.append((inst.name, status, msg))
        # Components, that by construction always have a configuration, 
        # additionally display their configuration status:
        if isinstance(inst, component):
            cfg = inst.check_config()
            if cfg is not None:
                config.append((inst.name, *cfg))

    # Eventually, display plugin components availability checks, filtered 
    # by role
    role_names = {c.name for c in role_comps} if role_comps is not None else None
    for plugin in PLUGIN_REGISTRY.plugins:
        if role_names is not None and plugin.name not in role_names:
            continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return config, avail
