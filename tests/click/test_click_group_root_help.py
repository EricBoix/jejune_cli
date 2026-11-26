import click
from click.testing import CliRunner

from jejune_cli.click import click_group_root
from jejune_cli.plugins.plugin_description import PluginDescription


@click.group()
def sample_plugin_group():
    """Sample plugin commands."""


def test_help_lists_a_plugin_under_its_target_role(monkeypatch):
    # The real loader reads the installed entry points: load the sample plugin
    # instead, through the same registry
    def load_sample_plugin(app):
        app.plugin_registry.register_plugin_component(
            PluginDescription(
                name="sample-plugin",
                group=sample_plugin_group,
                target_role="doc-steward",
            )
        )

    monkeypatch.setattr(click_group_root, "load_plugins", load_sample_plugin)
    monkeypatch.setenv("JEJUNE_ROLE", "doc-steward")
    result = CliRunner().invoke(click_group_root.cli, ["--help"])
    assert result.exit_code == 0, result.output
    assert "jejune sample-plugin" in result.output
