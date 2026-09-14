"""Aggregate health-check used by ``jejune doctor``."""

import sys
from pathlib import Path

from .component_registry import REGISTRY as COMP_REGISTRY
from .component_with_config import conf_comp as component
from .plugin_registry import PLUGIN_REGISTRY
from .role_registry import ROLE_REGISTRY


def run_avail() -> tuple[list[tuple[str, str, str]], list]:
    """Return (avail_results, active_components_components) — availability checks only.

    Used by availability subcommands that do not need configuration status.
    Each avail entry is (component_name, status, message).
    active_components_components are in topological order.
    """
    role_comps = ROLE_REGISTRY.current_role_components()
    if role_comps is None:
        print("This role does not have any components. Inquire on this case.")
        sys.exit()

    active_components = COMP_REGISTRY.sorted_active_set(role_comps)
    plugin_names = {p.name for p in PLUGIN_REGISTRY.plugins}
    role_names = {c.name for c in role_comps}

    avail: list[tuple[str, str, str]] = []
    for inst in active_components:
        if inst.name in plugin_names:
            continue
        status, msg = inst.check()
        avail.append((inst.name, status, msg))

    from .component_containerized import cont_comp

    for plugin in PLUGIN_REGISTRY.plugins:
        if plugin.name not in role_names:
            continue
        inst = COMP_REGISTRY.get(plugin.name)
        if isinstance(inst, cont_comp):
            status, msg = inst.check()
            if status != "ok":
                avail.append((plugin.name, status, msg))
                continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return avail, active_components


def run_all() -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
    list,
]:
    """Return (config_results, avail_results, active_components_components).

    Used by `jejune doctor`, which needs both configuration and availability status.
    Each result entry is (component_name, status, message).
    All source files are pre-loaded into os.environ before any config check runs,
    so that plugin components whose env vars are defined in a parent's source file
    (e.g. deployment.env) see the values regardless of topological order.
    """
    role_comps = ROLE_REGISTRY.current_role_components()
    if role_comps is None:
        print("This role does not have any components. Inquire on this case.")
        sys.exit()

    active_components = COMP_REGISTRY.sorted_active_set(role_comps)

    for inst in active_components:
        if isinstance(inst, component) and inst.configuration:
            inst.configuration.load(Path("."))

    config: list[tuple[str, str, str]] = []
    for inst in active_components:
        if not isinstance(inst, component) or not inst.configuration:
            continue
        status, msg, _ = inst.configuration.check()
        config.append((inst.name, status, msg))

    avail, _ = run_avail()

    return config, avail, active_components
