import click

from .click_comp_deployment import deployment, up as _up_cmd, down as _down_cmd
from .click_workspace_deployer import init as _deployer_init
from .click_workspace_doc_steward import init as _doc_steward_init


class AliasShim(click.BaseCommand):
    def __init__(self, wrapped: click.BaseCommand, canonical: str) -> None:
        super().__init__(name=wrapped.name)
        self._wrapped = wrapped
        self._canonical = canonical

    def get_short_help_str(self, limit: int = 150) -> str:
        return f"alias for: jejune {self._canonical}"

    def make_context(self, info_name, args, parent=None, **extra):
        return self._wrapped.make_context(info_name, args, parent=parent, **extra)

    def invoke(self, ctx: click.Context):
        return self._wrapped.invoke(ctx)

    def get_help(self, ctx: click.Context) -> str:
        return self._wrapped.get_help(ctx)


def register_aliases(
    cli: click.Group,
    document: click.Group,
) -> list[tuple[click.Group, str, click.BaseCommand, str, str]]:
    aliases: list[tuple[click.Group, str, click.BaseCommand, str, str]] = [
        (deployment, "init", _deployer_init, "configuration deployer init", "deployer"),
        (document, "init", _doc_steward_init, "configuration doc-steward init", "doc-steward"),
        (cli, "up", _up_cmd, "deployment up", "deployer"),
        (cli, "down", _down_cmd, "deployment down", "deployer"),
    ]
    for alias_group, alias_name, alias_cmd, alias_canonical, _ in aliases:
        alias_group.add_command(AliasShim(alias_cmd, alias_canonical), alias_name)
    return aliases
