"""Abstract base for external (user-installed) components."""

from jejune_cli.core.component_base import BaseComp


class ExtComp(BaseComp):
    """External dependency the user must install/provide.

    All ExtComp instances are hidden from `jejune components doctor` when available.
    """
