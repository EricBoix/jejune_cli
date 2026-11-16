"""RoleRegistry singleton and built-in role registrations."""

import os

from jejune_cli.core.component_registry import ComponentRegistry
from jejune_cli.plugin_role_description import PluginRoleDescription
from jejune_cli.core.component_base import BaseComp
from jejune_cli.roles.role import Role


class RoleRegistry:
    def __init__(self, component_registry: ComponentRegistry) -> None:
        self._component_registry = component_registry
        self._roles: dict[str, Role] = {}
        self._role_cache: dict[str, Role] = {}

    def register(self, role: Role) -> None:
        self._roles[role.name] = role
        self._role_cache.clear()

    def register_from_plugin(self, role_desc: "plugin_role_description") -> None:
        role = Role(
            name=role_desc.name,
            component_names=tuple(role_desc.components),
            includes=role_desc.includes,
            section_title=role_desc.section_title,
            detector=role_desc.detect,
            is_abstract=role_desc.abstract,
        )
        self._roles[role.name] = role
        for existing_name, additional_parents in role_desc.extend_includes.items():
            existing = self._roles.get(existing_name)
            if existing is not None:
                existing.includes = existing.includes + additional_parents
        self._role_cache.clear()

    def get(self, name: str) -> "Role | None":
        return self._roles.get(name)

    @property
    def roles(self) -> list[str]:
        return list(self._roles.keys())

    @property
    def abstract_roles(self) -> set[str]:
        return {name for name, role in self._roles.items() if role.is_abstract}

    @property
    def display_roles(self) -> "list[Role]":
        """Non-abstract roles (shown in --help)."""
        return [role for role in self._roles.values() if not role.is_abstract]

    def section_title(self, role_name: str) -> str:
        role = self._roles.get(role_name)
        return role.section_title if role else ""

    def description(self, role_name: str) -> str:
        role = self._roles.get(role_name)
        return role.description if role else ""

    def includes(self, role_name: str) -> tuple[str, ...]:
        role = self._roles.get(role_name)
        return role.includes if role else ()

    def current_role_components(self) -> "frozenset[BaseComp] | None":
        return self.role_components(self.detect_role())

    def detect_role_name(self) -> "str | None":
        return self.detect_role().name or None

    def detect_role(self) -> Role:
        cwd = os.getcwd()
        if cwd in self._role_cache:
            return self._role_cache[cwd]
        override = os.environ.get("JEJUNE_ROLE")
        if override:
            result = self._roles.get(override, Role.NONE)
        else:
            result = Role.NONE
            for role in self._roles.values():
                if role.detector is not None:
                    try:
                        if role.detector():
                            result = role
                            break
                    except Exception:
                        pass
        self._role_cache[cwd] = result
        return result

    def role_components(self, role: Role) -> "frozenset[BaseComp] | None":
        """Return the full component set for *role*, including inherited parent components."""
        if not role:
            return None
        registry = self._component_registry

        def _resolve(role: Role) -> "frozenset[BaseComp]":
            return frozenset(
                filter(
                    None,
                    (
                        registry.get(component_name)
                        for component_name in role.component_names
                    ),
                )
            )

        own = _resolve(role)
        for parent_name in role.includes:
            parent = self._roles.get(parent_name)
            if parent:
                own = own | _resolve(parent)
        return own or None

    def role_cli_commands(self, role: Role) -> list[str]:
        """Return CLI command names contributed by *role*'s components plus extra_commands."""
        registry = self._component_registry
        return [
            comp.cli_name
            for name in role.component_names
            if (comp := registry.get(name)) is not None and comp.cli_name is not None
        ] + list(role.extra_commands)

    def role_is_deployer_family(self, role: Role) -> bool:
        return self.role_inherits(role, "deployer")

    def role_is_doc_steward_family(self, role: Role) -> bool:
        return self.role_inherits(role, "doc-steward")

    def role_is_catalog_contributor_family(self, role: Role) -> bool:
        return self.role_inherits(role, "catalog-contributor")

    def role_is_deployment_catalog_family(self, role: Role) -> bool:
        return self.role_inherits(role, "deployment-catalog")

    def role_inherits(self, role: "Role | str", parent: str) -> bool:
        if not role:
            return False
        role_name = role.name if isinstance(role, Role) else role
        if role_name == parent:
            return True
        seen: set[str] = set()
        role_obj = self._roles.get(role_name)
        stack = list(role_obj.includes if role_obj else ())
        while stack:
            candidate_name = stack.pop()
            if candidate_name == parent:
                return True
            if candidate_name not in seen:
                seen.add(candidate_name)
                candidate_obj = self._roles.get(candidate_name)
                if candidate_obj:
                    stack.extend(candidate_obj.includes)
        return False

    def build_hierarchy_lines(self) -> list[str]:
        """Return lines for a UML box-style inheritance diagram of all roles."""

        def _reachable(role: str) -> set[str]:
            seen: set[str] = set()
            reachable_role = self._roles.get(role)
            stack = list(reachable_role.includes if reachable_role else ())
            while stack:
                candidate_name = stack.pop()
                if candidate_name not in seen:
                    seen.add(candidate_name)
                    candidate_role = self._roles.get(candidate_name)
                    if candidate_role:
                        stack.extend(candidate_role.includes)
            return seen

        parentless_role_names = [
            role_name
            for role_name, role_obj in self._roles.items()
            if not role_obj.includes
        ]
        if len(parentless_role_names) != 1:
            raise ValueError(
                "Role hierarchy needs exactly one root role (a role without includes), "
                f"found: {parentless_role_names}"
            )
        root = parentless_role_names[0]
        children: dict[str, list[str]] = {}
        for role_name in self._roles:
            if role_name == root:
                continue
            role_obj = self._roles[role_name]
            parents = list(role_obj.includes)
            for parent_name in parents:
                via_others: set[str] = set()
                for other_parent_name in parents:
                    if other_parent_name != parent_name:
                        via_others |= {other_parent_name} | _reachable(
                            other_parent_name
                        )
                if parent_name not in via_others:
                    children.setdefault(parent_name, []).append(role_name)

        horizontal_gap, box_padding = 4, 1

        def _box_width(name: str) -> int:
            return len(name) + 2 * box_padding + 2

        def _subtree_width(node: str) -> int:
            child_names = children.get(node, [])
            if not child_names:
                return _box_width(node)
            return max(
                _box_width(node),
                sum(_subtree_width(child_name) for child_name in child_names)
                + horizontal_gap * (len(child_names) - 1),
            )

        x_left: dict[str, int] = {}

        def _assign(node: str, left: int) -> None:
            x_left[node] = left
            child_names = children.get(node, [])
            if not child_names:
                return
            children_width = sum(
                _subtree_width(child_name) for child_name in child_names
            ) + horizontal_gap * (len(child_names) - 1)
            child_left = left + max(0, (_subtree_width(node) - children_width) // 2)
            for child_name in child_names:
                _assign(child_name, child_left)
                child_left += _subtree_width(child_name) + horizontal_gap

        _assign(root, 0)

        def _box_left(node: str) -> int:
            return x_left[node] + (_subtree_width(node) - _box_width(node)) // 2

        def _box_center(node: str) -> int:
            return _box_left(node) + _box_width(node) // 2

        levels: list[list[str]] = []
        current_level: list[str] = [root]
        while current_level:
            levels.append(current_level)
            next_level: list[str] = []
            for node_name in current_level:
                next_level.extend(children.get(node_name, []))
            current_level = next_level

        diagram_width = _subtree_width(root) + 2

        def _row() -> list[str]:
            return [" "] * diagram_width

        def _put(row: list[str], col: int, text: str) -> None:
            for offset, character in enumerate(text):
                if 0 <= col + offset < len(row):
                    row[col + offset] = character

        output: list[str] = []

        for level_index, level in enumerate(levels):
            top_row, middle_row, bottom_row = _row(), _row(), _row()
            for node_name in level:
                left_column, box_width_value = _box_left(node_name), _box_width(
                    node_name
                )
                _put(top_row, left_column, "┌" + "─" * (box_width_value - 2) + "┐")
                _put(
                    middle_row,
                    left_column,
                    "│" + " " * box_padding + node_name + " " * box_padding + "│",
                )
                _put(bottom_row, left_column, "└" + "─" * (box_width_value - 2) + "┘")
            output += [
                "".join(top_row).rstrip(),
                "".join(middle_row).rstrip(),
                "".join(bottom_row).rstrip(),
            ]

            if level_index == len(levels) - 1:
                break

            has_multi = any(len(children.get(node_name, [])) > 1 for node_name in level)

            if has_multi:
                stem_row, bar_row, drop_row = _row(), _row(), _row()
                _JUNCTION = {"─": "┴", "┌": "├", "┐": "┤", "┬": "┼"}
                for node_name in level:
                    child_names = children.get(node_name, [])
                    if not child_names:
                        continue
                    parent_center = _box_center(node_name)
                    _put(stem_row, parent_center, "│")
                    if len(child_names) == 1:
                        _put(bar_row, parent_center, "│")
                        _put(drop_row, _box_center(child_names[0]), "│")
                    else:
                        leftmost_center = min(
                            _box_center(child_name) for child_name in child_names
                        )
                        rightmost_center = max(
                            _box_center(child_name) for child_name in child_names
                        )
                        for column in range(leftmost_center, rightmost_center + 1):
                            bar_row[column] = "─"
                        for child_name in child_names:
                            child_center = _box_center(child_name)
                            bar_row[child_center] = (
                                "┌"
                                if child_center == leftmost_center
                                else ("┐" if child_center == rightmost_center else "┬")
                            )
                        bar_row[parent_center] = _JUNCTION.get(
                            bar_row[parent_center], "┴"
                        )
                        for child_name in child_names:
                            _put(drop_row, _box_center(child_name), "│")
                output += [
                    "".join(stem_row).rstrip(),
                    "".join(bar_row).rstrip(),
                    "".join(drop_row).rstrip(),
                ]
            else:
                stem_row = _row()
                for node_name in level:
                    if children.get(node_name):
                        _put(stem_row, _box_center(node_name), "│")
                output.append("".join(stem_row).rstrip())

        return output
