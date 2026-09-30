"""Wire plugin CLI commands and roles into the root CLI group."""

from .app_context import AppContext
from .click_group_configuration import register_role_config_subgroup
from .plugin_description import plugin_description


def load_plugins(app: AppContext) -> None:
    """Register the CLI post-hook and load all plugins for the detected role."""
    def _handle_plugin(plugin: plugin_description) -> None:
        app.cli.add_command(plugin.group, plugin.name)
        if plugin.role is not None:
            app.role_registry.register_from_plugin(plugin.role)
            if plugin.role.config_group is not None:
                register_role_config_subgroup(plugin.role.config_group)

    app.plugin_registry.add_post_hook(_handle_plugin)
    if app.role_registry.detect_role():
        app.plugin_registry.load_all()
