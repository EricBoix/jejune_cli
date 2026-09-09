"""RoleRegistry singleton and built-in role registrations."""

import os
from typing import TYPE_CHECKING

from .role import CONTRIBUTOR, DEPLOYER, DOC_STEWARD, NO_ROLE, Role

if TYPE_CHECKING:
    from .plugin_role_description import plugin_role_description
    from .component_base import base_comp


class RoleRegistry:
    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}
        self._pending_help_sections: list[tuple[str, str | None, int]] = []

    def register(self, role: Role) -> None:
        self._roles[role.name] = role

    def register_from_plugin(self, j: "plugin_role_description") -> None:
        from .component_registry import REGISTRY as COMP_REGISTRY
        components = frozenset(filter(None, (COMP_REGISTRY.get(n) for n in j.components)))
        role = Role(
            name=j.name,
            components=components,
            includes=j.includes,
            section_title=j.section_title,
            detector=j.detect,
            is_abstract=j.abstract,
        )
        self._roles[role.name] = role
        for existing_name, additional_parents in j.extend_includes.items():
            existing = self._roles.get(existing_name)
            if existing is not None:
                existing.includes = existing.includes + additional_parents

    def register_help_section(
        self,
        name: str,
        stage: str | None = None,
        order: int = 50,
    ) -> None:
        self._pending_help_sections.append((name, stage, order))

    def get(self, name: str) -> "Role | None":
        return self._roles.get(name)

    @property
    def roles(self) -> list[str]:
        return list(self._roles.keys())

    @property
    def abstract_roles(self) -> set[str]:
        return {name for name, r in self._roles.items() if r.is_abstract}

    @property
    def pending_help_sections(self) -> list[tuple[str, str | None, int]]:
        return self._pending_help_sections

    def section_title(self, role_name: str) -> str:
        r = self._roles.get(role_name)
        return r.section_title if r else ""

    def description(self, role_name: str) -> str:
        r = self._roles.get(role_name)
        return r.description if r else ""

    def includes(self, role_name: str) -> tuple[str, ...]:
        r = self._roles.get(role_name)
        return r.includes if r else ()

    def current_role_components(self) -> "frozenset[base_comp] | None":
        return self.role_components(self.detect_role())

    def detect_role_name(self) -> "str | None":
        return self.detect_role().name or None

    def detect_role(self) -> Role:
        override = os.environ.get("JEJUNE_ROLE")
        if override:
            return self._roles.get(override, NO_ROLE)
        for r in self._roles.values():
            if r.detector is not None:
                try:
                    if r.detector():
                        return r
                except Exception:
                    pass
        return NO_ROLE

    def role_components(self, role: Role) -> "frozenset[base_comp] | None":
        if not role:
            return None
        own = role.components
        for parent_name in role.includes:
            parent = self._roles.get(parent_name)
            if parent:
                own = own | parent.components
        return own or None

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
            r = stack.pop()
            if r == parent:
                return True
            if r not in seen:
                seen.add(r)
                r_obj = self._roles.get(r)
                if r_obj:
                    stack.extend(r_obj.includes)
        return False

    def build_hierarchy_lines(self) -> list[str]:
        """Return lines for a UML box-style inheritance diagram of all roles."""

        def _reachable(role: str) -> set[str]:
            seen: set[str] = set()
            r_obj = self._roles.get(role)
            stack = list(r_obj.includes if r_obj else ())
            while stack:
                r = stack.pop()
                if r not in seen:
                    seen.add(r)
                    r_obj2 = self._roles.get(r)
                    if r_obj2:
                        stack.extend(r_obj2.includes)
            return seen

        root = "contributor"
        children: dict[str, list[str]] = {}
        for role_name in self._roles:
            if role_name == root:
                continue
            role_obj = self._roles[role_name]
            parents = list(role_obj.includes)
            for p in parents:
                via_others: set[str] = set()
                for o in parents:
                    if o != p:
                        via_others |= {o} | _reachable(o)
                if p not in via_others:
                    children.setdefault(p, []).append(role_name)

        H_GAP, PAD = 4, 1

        def _bw(name: str) -> int:
            return len(name) + 2 * PAD + 2

        def _sw(node: str) -> int:
            kids = children.get(node, [])
            if not kids:
                return _bw(node)
            return max(_bw(node), sum(_sw(k) for k in kids) + H_GAP * (len(kids) - 1))

        x_left: dict[str, int] = {}

        def _assign(node: str, left: int) -> None:
            x_left[node] = left
            kids = children.get(node, [])
            if not kids:
                return
            kw = sum(_sw(k) for k in kids) + H_GAP * (len(kids) - 1)
            cur = left + max(0, (_sw(node) - kw) // 2)
            for k in kids:
                _assign(k, cur)
                cur += _sw(k) + H_GAP

        _assign(root, 0)

        def _bl(node: str) -> int:
            return x_left[node] + (_sw(node) - _bw(node)) // 2

        def _bc(node: str) -> int:
            return _bl(node) + _bw(node) // 2

        levels: list[list[str]] = []
        cur_lvl: list[str] = [root]
        while cur_lvl:
            levels.append(cur_lvl)
            nxt: list[str] = []
            for n in cur_lvl:
                nxt.extend(children.get(n, []))
            cur_lvl = nxt

        W = _sw(root) + 2

        def _row() -> list[str]:
            return [' '] * W

        def _put(r: list[str], col: int, s: str) -> None:
            for i, c in enumerate(s):
                if 0 <= col + i < len(r):
                    r[col + i] = c

        output: list[str] = []

        for lvl_i, level in enumerate(levels):
            tr, mr, br = _row(), _row(), _row()
            for n in level:
                bl, bw = _bl(n), _bw(n)
                _put(tr, bl, "┌" + "─" * (bw - 2) + "┐")
                _put(mr, bl, "│" + " " * PAD + n + " " * PAD + "│")
                _put(br, bl, "└" + "─" * (bw - 2) + "┘")
            output += ["".join(tr).rstrip(), "".join(mr).rstrip(), "".join(br).rstrip()]

            if lvl_i == len(levels) - 1:
                break

            has_multi = any(len(children.get(n, [])) > 1 for n in level)

            if has_multi:
                c1, c2, c3 = _row(), _row(), _row()
                _JOIN = {'─': '┴', '┌': '├', '┐': '┤', '┬': '┼'}
                for n in level:
                    kids = children.get(n, [])
                    if not kids:
                        continue
                    pc = _bc(n)
                    _put(c1, pc, "│")
                    if len(kids) == 1:
                        _put(c2, pc, "│")
                        _put(c3, _bc(kids[0]), "│")
                    else:
                        lm = min(_bc(k) for k in kids)
                        rm = max(_bc(k) for k in kids)
                        for x in range(lm, rm + 1):
                            c2[x] = '─'
                        for k in kids:
                            cc = _bc(k)
                            c2[cc] = '┌' if cc == lm else ('┐' if cc == rm else '┬')
                        c2[pc] = _JOIN.get(c2[pc], '┴')
                        for k in kids:
                            _put(c3, _bc(k), "│")
                output += ["".join(c1).rstrip(), "".join(c2).rstrip(), "".join(c3).rstrip()]
            else:
                c1 = _row()
                for n in level:
                    if children.get(n):
                        _put(c1, _bc(n), "│")
                output.append("".join(c1).rstrip())

        return output


ROLE_REGISTRY = RoleRegistry()

ROLE_REGISTRY.register(CONTRIBUTOR)
ROLE_REGISTRY.register(DOC_STEWARD)
ROLE_REGISTRY.register(DEPLOYER)
