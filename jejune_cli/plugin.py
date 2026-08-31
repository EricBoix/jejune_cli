"""Plugin protocol for jejune extensions.

Extension packages register a JejunePlugin instance via the entry-point group
"jejune.plugins".  Example pyproject.toml entry:

    [project.entry-points."jejune.plugins"]
    my-ext = "my_package.plugin:plugin"

where ``plugin`` is a ``JejunePlugin`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import click


@dataclass
class JejuneRole:
    """Role definition contributed by an extension package.

    When a JejunePlugin carries a role, jejune-cli registers it at startup so
    that the role becomes auto-detectable, its help section appears in
    ``jejune --help``, and (optionally) its config subgroup appears under
    ``jejune configuration``.

    Fields
    ------
    name             : role identifier, e.g. ``"my-role"``.
    components       : frozenset of component names owned by this role.
    includes         : parent roles whose components are inherited.
    detection_reason : human-readable indicator shown by ``jejune role``.
    section_title    : header for this role's section in ``jejune --help``.
    detect           : callable returning True when the cwd belongs to this role.
    help_stage       : plugin stage used to group plugin commands in ``--help``
                       (``"single-document"``, ``"collection"``, ``"extension"``).
    order            : insertion position among help sections (contributor=0,
                       doc-steward=10, deployer=90; defaults to 50).
    abstract         : if True, the role appears in ``jejune role list`` annotated as
                       abstract but cannot be set via ``jejune role set``.  Use for
                       roles that are only ever reached through inheritance.
    config_group     : if set, added as a subgroup of ``jejune configuration``.
    extend_includes  : mapping of *existing* role names to additional parent
                       tuples to splice in at registration time.  Use this to
                       make an existing role inherit from the new one.
                       e.g. ``{"deployer": ("my-role",)}`` causes the deployer
                       role to inherit my-role when the plugin is installed.
    """

    name: str
    components: frozenset[str]
    includes: tuple[str, ...]
    detection_reason: str
    section_title: str
    detect: Callable[[], bool]
    help_stage: str
    order: int = 50
    abstract: bool = False
    config_group: click.Group | None = None
    extend_includes: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass
class JejunePlugin:
    """Contract between jejune-cli and an extension package.

    Mandatory fields
    ----------------
    name  : component name as it will appear in ``jejune --help`` and
            ``jejune doctor`` (e.g. ``"rob-burbea"``).
    group : the Click Group that provides the component's subcommands.

    Optional fields (all default to "no information")
    --------------------------------------------------
    config_vars         : env vars required for this component.
    config_hint         : what to do when they are missing.
    avail_hint          : shown in doctor Availability table on error
                          (e.g. ``"run `jejune rob-burbea status`"``).
    check_availability  : () -> (ok, message) — probes the component's
                          service at runtime.  When None the doctor row
                          shows "warn / no availability check".
    required_deps       : names of components that must be ok first.
    optional_deps       : names of components that enhance this one.
    stage               : controls which ``jejune --help`` section lists
                          this component — ``"single-document"``,
                          ``"collection"``, or ``"extension"`` (default).
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
    kind: str = ""
    """Component nature shown in the ``jejune doctor`` Kind column.

    ``"dep"``  → external dependency the user must install/provide.
    ``""``     → mandatory jejune-managed component (default; no label shown).
    """
    role: JejuneRole | None = None
    build_image: Callable[[bool], None] | None = None
    """(no_cache: bool) -> None — builds this component's Docker image.

    When set, main._load_plugins() registers it automatically via register_build().
    """
    image_is_built: Callable[[], bool] | None = None
    """() -> bool — returns True when this component's Docker image already exists."""


# Populated at startup by main._load_plugins().  Read by _health.run_all().
_REGISTRY: list[JejunePlugin] = []
