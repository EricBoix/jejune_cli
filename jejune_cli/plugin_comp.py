"""Minimal component type for plugins that declare no custom component."""

from .component_with_config import conf_comp


class PluginComp(conf_comp):
    """Component registered automatically for plugins that declare no custom component."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def check(self) -> tuple[str, str]:
        return "ok", ""
