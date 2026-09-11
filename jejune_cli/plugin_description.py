"""Plugin package description — the contract between jejune-cli and a plugin package.

Plugin packages register a plugin_description instance via the entry-point group
"jejune.plugins".  Example pyproject.toml entry:

    [project.entry-points."jejune.plugins"]
    my-ext = "my_package.plugin:plugin"

where ``plugin`` is a ``plugin_description`` instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

import click

from .plugin_role_description import plugin_role_description

if TYPE_CHECKING:
    from .component_base import base_comp


@dataclass
class plugin_description:
    """Contract between jejune-cli and a plugin package.

    Mandatory fields
    ----------------
    name  : component name as it will appear in ``jejune --help`` and
            ``jejune doctor`` (e.g. ``"kg-viewer"``).
    group : the Click Group that provides the component's subcommands.

    Optional fields
    ---------------
    config_vars        : env vars required for this component.
    config_hint        : what to do when they are missing.
    avail_hint         : shown in doctor Availability table on error.
    check_availability : () -> (ok, message) — runtime probe.
    required_deps      : names of built-in components that must be ok first.
    optional_deps      : names of components that enhance this one.
    stage              : controls which ``jejune --help`` section lists this
                         component — ``"single-document"``, ``"collection"``,
                         or ``"extension"`` (default).
    role               : role contributed by this plugin package.
    build_image        : (no_cache: bool) -> None — builds Docker image.
    image_is_built     : () -> bool — checks if Docker image exists.
    component          : optional full base_comp instance to register in
                         COMP_REGISTRY instead of a thin wrapper.  Use when
                         the plugin contributes a containerized component that
                         needs rich Docker lifecycle methods.
    """

    name: str
    group: click.Group
    config_vars: list[str] = field(default_factory=list)
    config_hint: str = ""
    avail_hint: str = ""
    check_availability: Callable[[], tuple[bool, str]] | None = None
    required_deps: list[str] = field(default_factory=list)
    optional_deps: list[str] = field(default_factory=list)
    stage: str = "extension"
    """Determines the ``jejune --help`` section for this component.

    ``"single-document"``  → "Single-document extension components"
    ``"collection"``       → "Collection-level extension components"
    ``"extension"``        → "Extension components" (default)
    """
    role: plugin_role_description | None = None
    build_image: Callable[[bool], None] | None = None
    """(no_cache: bool) -> None — builds this component's Docker image."""
    image_is_built: Callable[[], bool] | None = None
    """() -> bool — returns True when this component's Docker image already exists."""
    component: "base_comp | None" = None
    """Full component instance to register in COMP_REGISTRY.

    When set, PluginRegistry uses this instance directly instead of creating a
    thin _PluginComp wrapper.  The instance must have name == self.name.
    """
    repo_name: str | None = None
    """Git repository name when it differs from the distribution package name.

    Used by the plugin registry to map ``plugin_deps`` repo names to plugin
    names when the distribution name (normalised) does not match the repo name.
    Example: repo ``jejune_kg-graph_viewer`` distributes as ``jejune-kg-viewer``,
    so the plugin sets ``repo_name="jejune_kg-graph_viewer"``.
    """

