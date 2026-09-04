"""Abstract base for external (user-installed) components."""
from .component_base import base_comp


class ext_comp(base_comp):
    """External dependency the user must install/provide.

    All ext_comp instances are hidden from `jejune doctor` when available.
    """
