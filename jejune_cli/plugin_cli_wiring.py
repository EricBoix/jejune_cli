"""Wire plugin CLI commands and roles into the root CLI group."""
from .click_group_root import cli
from .click_group_configuration import register_role_config_subgroup
from .plugin_description import plugin_description
from .plugin_registry import PLUGIN_REGISTRY
from .role_registry import ROLE_REGISTRY


def _handle_plugin(plugin: plugin_description) -> None:
    cli.add_command(plugin.group, plugin.name)
    if plugin.role is not None:
        ROLE_REGISTRY.register_from_plugin(plugin.role)
        if plugin.role.config_group is not None:
            register_role_config_subgroup(plugin.role.config_group)


def load_plugins() -> None:
    """Register the CLI post-hook and load all plugins for the detected role."""
    PLUGIN_REGISTRY.add_post_hook(_handle_plugin)
    if ROLE_REGISTRY.detect_role():
        PLUGIN_REGISTRY.load_all()
