"""Aggregate health-check used by ``jejune components doctor``."""

import sys

from .component_base import base_comp
from .component_registry import ComponentRegistry
from .component_containerized import cont_comp
from .component_with_config import conf_comp
from .plugin_registry import PluginRegistry
from .role_registry import RoleRegistry


def run_avail(
    component_registry: ComponentRegistry,
    role_registry: RoleRegistry,
    plugin_registry: PluginRegistry,
) -> tuple[list[tuple[str, str, str]], list[base_comp]]:
    """Return (avail_results, active_components) — availability checks only.

    Used by availability subcommands that do not need configuration status.
    Each avail entry is (component_name, status, message).
    active_components are in topological order.
    """
    role_comps = role_registry.current_role_components()
    if role_comps is None:
        print("This role does not have any components. Inquire on this case.")
        sys.exit()

    active_components = component_registry.sorted_active_set(role_comps)
    plugin_names = {p.name for p in plugin_registry.plugins}
    role_names = {c.name for c in role_comps}

    avail: list[tuple[str, str, str]] = []
    for inst in active_components:
        if inst.name in plugin_names:
            continue
        status, msg = inst.check()
        avail.append((inst.name, status, msg))

    for plugin in plugin_registry.plugins:
        if plugin.name not in role_names:
            continue
        inst = component_registry.get(plugin.name)
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


def run_all(
    component_registry: ComponentRegistry,
    role_registry: RoleRegistry,
    plugin_registry: PluginRegistry,
) -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
    list[base_comp],
]:
    """Return (config_results, avail_results, active_components).

    Used by `jejune components doctor`, which needs both configuration and availability status.
    Each result entry is (component_name, status, message).
    """
    role_comps = role_registry.current_role_components()
    if role_comps is None:
        print("This role does not have any components. Inquire on this case.")
        sys.exit()

    active_components = component_registry.sorted_active_set(role_comps)

    config: list[tuple[str, str, str]] = []
    for inst in active_components:
        if not isinstance(inst, conf_comp):
            continue
        status, msg = inst.check_config()
        config.append((inst.name, status, msg))

    avail, _ = run_avail(component_registry, role_registry, plugin_registry)

    return config, avail, active_components
