"""AppContext — single owner of all registries and the root CLI group."""
from __future__ import annotations

from pathlib import Path

import click

from .component_registry import ComponentRegistry
from .role_registry import RoleRegistry
from .containers_cross_process_coordination import ContainerCoordination
from .plugin_registry import PluginRegistry
from .plugin_package_catalog import plugin_package_catalog
from .heuristic_step_registry import HeuristicStepRegistry
from .component_building import build_components
from .role_definitions import wire_roles
from .heuristic_step_wiring import wire_heuristics


class AppContext:
    def __init__(self, cli: click.Group) -> None:
        self.cli                     = cli
        self.component_registry      = ComponentRegistry()
        self.role_registry           = RoleRegistry(self.component_registry)
        self.coordination            = ContainerCoordination()
        self.plugin_registry         = PluginRegistry(self.component_registry)
        catalog                      = plugin_package_catalog(
            self.component_registry,
            self.role_registry,
            self.plugin_registry,
        )
        self.heuristic_step_registry = HeuristicStepRegistry(self.role_registry)

        build_components(
            self.component_registry,
            self.coordination,
            catalog,
            self.role_registry,
            self.plugin_registry,
        )
        wire_roles(self.role_registry)

        wire_heuristics(
            self.heuristic_step_registry,
            self.component_registry,
            self.role_registry,
        )

        self.component_registry.load_all_configurations(Path.cwd())
