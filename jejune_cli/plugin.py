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
    """

    name: str
    group: click.Group
    config_vars: list[str] = field(default_factory=list)
    config_hint: str = ""
    avail_hint: str = ""
    check_availability: Callable[[], tuple[bool, str]] | None = None
    required_deps: list[str] = field(default_factory=list)
    optional_deps: list[str] = field(default_factory=list)


# Populated at startup by main._load_plugins().  Read by catalog.run_all().
_REGISTRY: list[JejunePlugin] = []
