"""Aggregate health-check used by ``jejune doctor``."""

import sys

from .component_registry import REGISTRY as COMP_REGISTRY
from .component_with_config import conf_comp as component
from .plugin_registry import PLUGIN_REGISTRY
from .role_registry import ROLE_REGISTRY


def run_avail() -> tuple[list[tuple[str, str, str]], list]:
    """Return (avail_results, visible_components) — availability checks only.

    Used by availability subcommands that do not need configuration status.
    Each avail entry is (component_name, status, message).
    visible_components are in topological order.
    """
    role_comps = ROLE_REGISTRY.current_role_components()
    if role_comps is None:
        print("This role does not have any components. Inquire on this case.")
        sys.exit()

    visible = COMP_REGISTRY.sorted_active_set(role_comps)
    plugin_names = {p.name for p in PLUGIN_REGISTRY.plugins}
    role_names = {c.name for c in role_comps}

    avail: list[tuple[str, str, str]] = []
    for inst in visible:
        if inst.name in plugin_names:
            continue
        status, msg = inst.check()
        avail.append((inst.name, status, msg))

    for plugin in PLUGIN_REGISTRY.plugins:
        if plugin.name not in role_names:
            continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return avail, visible


def run_all() -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
    list,
]:
    """Return (config_results, avail_results, visible_components).

    Used by `jejune doctor`, which needs both configuration and availability status.
    Each result entry is (component_name, status, message).
    """
    avail, visible = run_avail()
    plugin_names = {p.name for p in PLUGIN_REGISTRY.plugins}

    config: list[tuple[str, str, str]] = []
    for inst in visible:
        if not isinstance(inst, component):
            continue
        if inst.configuration.env_vars:
            status, msg, _ = inst.configuration.check()
            config.append((inst.name, status, msg))
        if inst.name not in plugin_names:
            cfg = inst.check_config()
            if cfg is not None:
                config.append((inst.name, *cfg))

    return config, avail, visible
