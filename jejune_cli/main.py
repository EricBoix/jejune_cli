import importlib.metadata
import subprocess
from pathlib import Path

import click

from ._env import dot_jejune, load_env_files
from ._health import run_all  # noqa: F401 — re-exported for external callers
from ._doctor import (
    _PLUGIN_OPTIONAL_DEPS,
    availability,
    config_check_availability,
    config_hint_availability,
    config_status_availability,
    doctor,
)
from ._next_cmd import next_cmd, register_heuristics
from ._role_cmd import role
from .convert import convert, convert_configured
from .plugin import JejunePlugin, _REGISTRY
from .role import register_role
from .deployment import deployment
from .click_comp_ecosystem import ecosystem
from .extensions import extensions_group

document = click.Group("document", help="Document workspace commands.")
from .ui_deployment import up as _up_cmd, down as _down_cmd
from .click_comp_configuration import (
    configuration,
    print_config_table,
    print_two_col_table,
    register_role_config_subgroup,
)
from . import containers
from .containers import containers_cli
from .graph import graph
from .llm import llm
from .manifest import manifest
from .llm_observability import llm_observability
from .click_comp_neo4j import neo4j
from .configuration_deployer import init as _deployer_init
from .configuration_doc_steward import init as _doc_steward_init
from .next_steps import has_heuristics_for_role, command_viable, register_command_precondition, print_next_steps
from .role import detect_roles, role_components, ROLES, ROLE_SECTION_TITLE, _ROLE_INCLUDES, build_hierarchy_lines, _PENDING_HELP_SECTIONS

_ACTIVE_ROLES, _ACTIVE_ROLE_REASON = detect_roles()
_ACTIVE_ROLE: str | None = _ACTIVE_ROLES[0] if _ACTIVE_ROLES else None
_ACTIVE_COMPONENTS = role_components(_ACTIVE_ROLES)


def _doctor_viable() -> bool:
    return not (_ACTIVE_ROLE in (None, "doc-steward") and not dot_jejune().is_dir())


register_command_precondition("jejune doctor", _doctor_viable)


# ---------------------------------------------------------------------------
# Component registry
# ---------------------------------------------------------------------------

from .component_base import base_comp
COMP_REGISTRY = base_comp.registry

_BUILTIN_COMPONENTS: frozenset[str] = frozenset(COMP_REGISTRY.names())

_CONTRIBUTOR_COMMANDS = ["doctor", "configuration", "role", "containers", "ecosystem", "next"]
_DOC_STEWARD_COMPONENTS = ["neo4j", "llm", "llm-observability", "graph", "convert", "manifest"]
_DEPLOYER_COMPONENTS = ["deployment"]

_ROLE_HELP_SECTIONS: list[tuple[str, list[str], str | None]] = [
    ("contributor", _CONTRIBUTOR_COMMANDS,   None),
    ("doc-steward", _DOC_STEWARD_COMPONENTS, "single-document"),
    ("deployer",    _DEPLOYER_COMPONENTS,    "extension"),
]

_SECTION_ORDER: dict[str, int] = {
    "contributor": 0,
    "doc-steward": 10,
    "deployer":    90,
}


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

class _JejuneGroup(click.Group):
    def invoke(self, ctx: click.Context) -> object:
        cmd_name = ctx._protected_args[0] if ctx._protected_args else None
        try:
            result = super().invoke(ctx)
        except SystemExit as exc:
            if exc.code == 0 and cmd_name != "next":
                print_next_steps()
            raise
        if cmd_name != "next":
            print_next_steps()
        return result

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        prefix = f"Usage [{_ACTIVE_ROLE}]: " if _ACTIVE_ROLE in ROLES else "Usage: "
        formatter.write_usage(ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...", prefix=prefix)

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        load_env_files()

        _hidden_unless_configured = {
            "convert": lambda: convert_configured() or Path.cwd().joinpath("full-catalog.yaml").exists(),
            "next": lambda: has_heuristics_for_role(_ACTIVE_ROLE),
        }

        def _row(name: str) -> tuple[str, str] | None:
            guard = _hidden_unless_configured.get(name)
            if guard is not None and not guard():
                return None
            cmd = self.get_command(ctx, name)
            if cmd and not cmd.hidden:
                return (f"jejune {name}", cmd.get_short_help_str(limit=formatter.width))
            return None

        def _rows(names: list[str]) -> list[tuple[str, str]]:
            return [r for name in names if (r := _row(name))]

        def _plugin_rows(stage: str) -> list[tuple[str, str]]:
            return [
                (f"jejune {p.name}", p.group.get_short_help_str(limit=formatter.width))
                for p in _REGISTRY if p.stage == stage
            ]

        _included = set(_ROLE_INCLUDES.get(_ACTIVE_ROLE, ()))
        for role_name, commands, plugin_stage in _ROLE_HELP_SECTIONS:
            if _ACTIVE_ROLE in ROLES and role_name not in {_ACTIVE_ROLE} | _included:
                continue
            rows = _rows(commands)
            if plugin_stage:
                rows += _plugin_rows(plugin_stage)
            rows += [
                (f"jejune {name}", f"alias for: jejune {canonical}")
                for grp, name, _, canonical, alias_role in _ALIASES
                if alias_role == role_name and grp is self
            ]
            if rows:
                with formatter.section(ROLE_SECTION_TITLE[role_name]):
                    formatter.write_dl(rows)


def _version_string() -> str:
    version = importlib.metadata.version("jejune-cli")
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").is_dir():
            try:
                sha = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, check=True,
                    cwd=candidate,
                ).stdout.strip()
                if sha:
                    return f"{version} ({sha})"
            except Exception:
                pass
            break
    try:
        from ._sha import SHA
        if SHA:
            return f"{version} ({SHA})"
    except ImportError:
        pass
    return version


@click.group(cls=_JejuneGroup)
@click.version_option(version=_version_string(), prog_name="jejune")
def cli():
    """jejune — jejuneness workflow CLI.

    Run `jejune configuration <role> init` to set up a new workspace.
    """
    load_env_files()


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

cli.add_command(configuration)
configuration.add_command(config_check_availability)
configuration.add_command(config_status_availability)
configuration.add_command(config_hint_availability)
cli.add_command(containers_cli)
cli.add_command(neo4j)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(manifest)
cli.add_command(deployment)
cli.add_command(document)
cli.add_command(ecosystem)
cli.add_command(extensions_group, "extensions")
cli.add_command(convert)
cli.add_command(availability)
cli.add_command(doctor)
cli.add_command(role)
cli.add_command(next_cmd, "next")

# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

_ALIASES: list[tuple[click.Group, str, click.BaseCommand, str, str]] = [
    (deployment, "init", _deployer_init,    "configuration deployer init",    "deployer"),
    (document,   "init", _doc_steward_init, "configuration doc-steward init", "doc-steward"),
    (cli,        "up",   _up_cmd,        "deployment up",               "deployer"),
    (cli,        "down", _down_cmd,      "deployment down",             "deployer"),
]


class _AliasShim(click.BaseCommand):
    """Proxy that delegates execution to a wrapped command but annotates itself as an alias."""

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


for _alias_group, _alias_name, _alias_cmd, _alias_canonical, _ in _ALIASES:
    _alias_group.add_command(_AliasShim(_alias_cmd, _alias_canonical), _alias_name)


# ---------------------------------------------------------------------------
# Registry-driven build command
# ---------------------------------------------------------------------------

@cli.command("build")
@click.option("--no-cache", is_flag=True, default=False,
              help="Do not use cache when building images.")
def build(no_cache: bool) -> None:
    """Build Docker images for all components in the current role.

    Each component that owns a Docker image registers its builder automatically.
    Use `jejune deployment build <dir>` to build a specific deployment directory.
    """
    from .component_containerized import cont_comp
    components = role_components(_ACTIVE_ROLES) or set()
    builders = [
        inst for inst in COMP_REGISTRY
        if isinstance(inst, cont_comp) and inst.name in components and inst.build_context
    ]
    if not builders:
        raise click.UsageError(
            f"'jejune build' has no Docker images registered for role {_ACTIVE_ROLE!r}."
        )
    for inst in builders:
        inst.build(no_cache)


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------

from .component_internal import component as _component


class _PluginComp(_component):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        return "ok", ""


def _load_plugins() -> None:
    global _ACTIVE_ROLE, _ACTIVE_ROLE_REASON, _ACTIVE_ROLES, _ACTIVE_COMPONENTS
    for ep in importlib.metadata.entry_points(group="jejune.plugins"):
        try:
            plugin: JejunePlugin = ep.load()
        except Exception as exc:
            click.echo(f"Warning: failed to load plugin {ep.name!r}: {exc}", err=True)
            continue
        _COMP_REGISTRY.append(plugin)
        cli.add_command(plugin.group, plugin.name)
        _PluginComp(
            name=plugin.name,
            dependencies=plugin.required_deps or [],
            hint=plugin.avail_hint,
        )
        if plugin.optional_deps:
            _PLUGIN_OPTIONAL_DEPS[plugin.name] = plugin.optional_deps
        if plugin.config_vars:
            inst = COMP_REGISTRY.get(plugin.name)
            if inst is not None:
                inst.configuration.env_vars = plugin.config_vars
                inst.configuration.hint = plugin.config_hint
        if plugin.role is not None:
            _register_plugin_role(plugin)
    for pending_name, pending_stage, pending_order in _PENDING_HELP_SECTIONS:
        if not any(rn == pending_name for rn, _, _ in _ROLE_HELP_SECTIONS):
            insert_at = next(
                (i for i, (rn, _, _) in enumerate(_ROLE_HELP_SECTIONS)
                 if _SECTION_ORDER.get(rn, 50) > pending_order),
                len(_ROLE_HELP_SECTIONS),
            )
            _ROLE_HELP_SECTIONS.insert(insert_at, (pending_name, [], pending_stage))
            _SECTION_ORDER[pending_name] = pending_order
    _ACTIVE_ROLES, _ACTIVE_ROLE_REASON = detect_roles()
    _ACTIVE_ROLE = _ACTIVE_ROLES[0] if _ACTIVE_ROLES else None
    _ACTIVE_COMPONENTS = role_components(_ACTIVE_ROLES)


def _register_plugin_role(plugin: JejunePlugin) -> None:
    """Register a role contributed by a plugin and insert its help section."""
    role_obj = plugin.role
    assert role_obj is not None
    register_role(role_obj)
    order = role_obj.order
    insert_at = next(
        (i for i, (rn, _, _) in enumerate(_ROLE_HELP_SECTIONS)
         if _SECTION_ORDER.get(rn, 50) > order),
        len(_ROLE_HELP_SECTIONS),
    )
    _ROLE_HELP_SECTIONS.insert(insert_at, (role_obj.name, [], role_obj.help_stage))
    _SECTION_ORDER[role_obj.name] = order
    if role_obj.config_group is not None:
        register_role_config_subgroup(role_obj.config_group)


_load_plugins()
register_heuristics()
