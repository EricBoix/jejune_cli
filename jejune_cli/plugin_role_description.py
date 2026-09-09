"""Role description contributed by a plugin package."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import click


@dataclass
class plugin_role_description:
    """Role definition contributed by a plugin package.

    When a plugin_description carries a role, jejune-cli registers it at startup
    so that the role becomes auto-detectable, its help section appears in
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
    abstract         : if True, the role appears in ``jejune role list`` annotated
                       as abstract but never directly detected.
    config_group     : if set, added as a subgroup of ``jejune configuration``.
    extend_includes  : mapping of *existing* role names to additional parent
                       tuples to splice in at registration time.
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
