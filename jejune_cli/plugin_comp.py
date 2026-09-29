"""Minimal component type for plugins that declare no custom component."""

from .component_registry import ComponentRegistry
from .component_with_config import conf_comp


class PluginComp(conf_comp):
    """Component registered automatically for plugins that declare no custom component."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ComponentRegistry().add(self)

    def check(self) -> tuple[str, str]:
        return "ok", ""
