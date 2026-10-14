"""Stub component for a plugin whose entry-point module failed to import."""

from .plugin_comp import PluginComp


class BrokenPluginComp(PluginComp):
    """Registered when ep.load() raises so that doctor/components-list surface the failure."""

    def check(self) -> tuple[str, str]:
        return "error", "plugin module failed to import"
