"""The `jejune components tree` command."""

import click

from .app_context import AppContext
from .component_base import BaseComp
from .click_theme import ClickTheme


def build_tree_lines(components: list[BaseComp]) -> list[str]:
    by_name = {component.name: component for component in components}

    # Top-level within the active set = not required by any other active component
    required: set[str] = {
        dep.name
        for comp in components
        for dep in comp.dependencies
        if dep.name in by_name
    }
    top_level = [
        component for component in components if component.name not in required
    ]

    visited: set[str] = set()
    status_cache: dict[str, tuple[str, str]] = {}

    def _status_icon(name: str) -> str:
        if name not in status_cache:
            comp = by_name.get(name)
            status_cache[name] = comp.check() if comp else ("error", "")
        status, _ = status_cache[name]
        icon, fg = ClickTheme.status_icons.get(status, ("?", "white"))
        return click.style(icon, fg=fg)

    def _render_children(comp_name: str, prefix: str) -> None:
        comp = by_name.get(comp_name)
        if comp is None:
            return
        children: list[tuple[str, str]] = (
            [(dependency.name, "") for dependency in comp.dependencies]
            + [(dependency.name, "[opt] ") for dependency in comp.optional_dependencies]
            + [
                (dependency.name, "[cond] ")
                for _, dependency in comp.conditional_dependencies
            ]
        )
        for index, (dep_name, label) in enumerate(children):
            is_last = index == len(children) - 1
            conn = "└── " if is_last else "├── "
            back = " [↑]" if dep_name in visited else ""
            lines.append(
                f"{prefix}{conn}{label}{dep_name} {_status_icon(dep_name)}{back}"
            )
            if dep_name not in visited:
                visited.add(dep_name)
                _render_children(dep_name, prefix + ("    " if is_last else "│   "))

    lines: list[str] = []
    for index, comp in enumerate(top_level):
        lines.append(f"{comp.name} {_status_icon(comp.name)}")
        if comp.name not in visited:
            visited.add(comp.name)
            _render_children(comp.name, "")
        if index < len(top_level) - 1:
            lines.append("")
    return lines


@click.command("tree")
@click.pass_context
def components_tree(ctx) -> None:
    """Show component dependency relationships as an ASCII tree."""
    app = ctx.find_object(AppContext)
    current_role_active_components: list[BaseComp] = (
        app.component_registry.sorted_active_set(
            app.role_registry.current_role_components()
        )
    )
    for line in build_tree_lines(current_role_active_components):
        click.echo(line)
