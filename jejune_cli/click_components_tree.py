"""The `jejune components tree` command."""

import click

from .component_registry import REGISTRY as COMP_REGISTRY
from .click_theme import ClickTheme


def build_tree_lines() -> list[str]:
    by_name = {c.name: c for c in COMP_REGISTRY}

    # Top-level = not in anyone's required dependencies
    required: set[str] = {dep.name for comp in COMP_REGISTRY for dep in comp.dependencies}
    top_level = [c for c in COMP_REGISTRY if c.name not in required]

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
            [(d.name, "") for d in comp.dependencies]
            + [(d.name, "[opt] ") for d in comp.optional_dependencies]
            + [(d.name, "[cond] ") for _, d in comp.conditional_dependencies]
        )
        for i, (dep_name, label) in enumerate(children):
            is_last = i == len(children) - 1
            conn = "└── " if is_last else "├── "
            back = " [↑]" if dep_name in visited else ""
            lines.append(f"{prefix}{conn}{label}{dep_name} {_status_icon(dep_name)}{back}")
            if dep_name not in visited:
                visited.add(dep_name)
                _render_children(dep_name, prefix + ("    " if is_last else "│   "))

    lines: list[str] = []
    for i, comp in enumerate(top_level):
        lines.append(f"{comp.name} {_status_icon(comp.name)}")
        if comp.name not in visited:
            visited.add(comp.name)
            _render_children(comp.name, "")
        if i < len(top_level) - 1:
            lines.append("")
    return lines


@click.command("tree")
def components_tree() -> None:
    """Show component dependency relationships as an ASCII tree."""
    for line in build_tree_lines():
        click.echo(line)
