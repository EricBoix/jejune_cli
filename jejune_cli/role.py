"""Role detection for jejune_cli.

Roles restrict `--help` output and `doctor` checks to what is relevant
for the active user persona. Role is inferred from the current directory;
the JEJUNE_ROLE env var overrides auto-detection.

Plugins can register additional roles at startup via ``register_role()``.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .plugin import JejuneRole

ROLES: list[str] = ["doc-steward", "deployer", "contributor"]
_DISPLAY_ROLES = ROLES

_ROLE_COMPONENTS: dict[str, frozenset[str]] = {
    "contributor": frozenset({"ecosystem", "network", "git-command", "git-repos-access"}),
    "doc-steward": frozenset(
        {"docker", "dockerhub", "pypi", "neo4j", "llm", "llm-observability", "graph", "convert", "manifest"}
    ),
    # "deployment" = built-in; UI service names come from installed check/ plugins.
    "deployer": frozenset({"docker", "extensions", "catalog", "deployment", "docs-server", "kg-viewer", "md-browser"}),
}

_ROLE_INCLUDES: dict[str, tuple[str, ...]] = {
    "deployer":    ("contributor",),
    "doc-steward": ("contributor",),
}

_ROLE_REASON: dict[str, str] = {
    "contributor": "inherited only",
    "doc-steward": ".jejune/ directory detected",
    "deployer": "docker-compose.yml detected",
}

_ROLE_DESCRIPTION: dict[str, str] = {
    "contributor": "base ecosystem role",
    "doc-steward": "document authoring",
    "deployer": "service deployment",
}

ROLE_SECTION_TITLE: dict[str, str] = {
    "contributor": "Contributor commands",
    "doc-steward": "Doc-steward commands",
    "deployer": "Deployer commands",
}

_ABSTRACT_ROLES: set[str] = set()

_ROLE_DETECTORS: list[tuple[str, Callable[[], bool]]] = []

# Help-section entries for abstract roles pre-registered at import time (before
# _load_plugins runs).  Populated by register_role_help_section(); consumed once
# by main._load_plugins() which inserts them into _ROLE_HELP_SECTIONS.
_PENDING_HELP_SECTIONS: list[tuple[str, str | None, int]] = []


def register_role_help_section(
    name: str,
    stage: str | None = None,
    order: int = 50,
) -> None:
    """Queue a help-section entry for an abstract role pre-registered via register_role().

    ``main._load_plugins()`` processes this list at startup and inserts entries
    into ``_ROLE_HELP_SECTIONS`` in the correct order position.
    """
    _PENDING_HELP_SECTIONS.append((name, stage, order))


def register_role(role: "JejuneRole") -> None:
    """Register a dynamically-defined role contributed by a plugin."""
    ROLES.append(role.name)
    _ROLE_COMPONENTS[role.name] = role.components
    _ROLE_INCLUDES[role.name] = role.includes
    _ROLE_REASON[role.name] = role.detection_reason
    ROLE_SECTION_TITLE[role.name] = role.section_title
    _ROLE_DETECTORS.append((role.name, role.detect))
    if role.abstract:
        _ABSTRACT_ROLES.add(role.name)
    for existing_role, additional_parents in role.extend_includes.items():
        _ROLE_INCLUDES[existing_role] = (
            _ROLE_INCLUDES.get(existing_role, ()) + additional_parents
        )


def detect_roles() -> list[str]:
    """Return all valid roles listed in .jejune/role (or the single detected role)."""
    override = os.environ.get("JEJUNE_ROLE")
    if override:
        return [override] if override in ROLES else []
    try:
        cwd = Path.cwd()
    except FileNotFoundError:
        return []
    role_file = cwd / ".jejune" / "role"
    if role_file.is_file():
        return [r.strip() for r in role_file.read_text().strip().split(",")
                if r.strip() in ROLES]
    primary, _ = detect_role()
    return [primary] if primary else []


def detect_role() -> tuple[str | None, str]:
    """Return (role, reason). Override with JEJUNE_ROLE env var."""
    override = os.environ.get("JEJUNE_ROLE")
    if override:
        if override in ROLES:
            return override, f"JEJUNE_ROLE={override}"
        return None, f"JEJUNE_ROLE={override!r} is not a known role (ignored)"
    try:
        cwd = Path.cwd()
    except FileNotFoundError:
        return None, "current directory is inaccessible"
    role_file = cwd / ".jejune" / "role"
    if role_file.is_file():
        role = role_file.read_text().strip().split(",")[0].strip()
        if role in ROLES:
            return role, ".jejune/role"
    if (cwd / "docker-compose.yml").exists():
        return "deployer", _ROLE_REASON["deployer"]
    if (cwd / ".jejune").is_dir():
        return "doc-steward", _ROLE_REASON["doc-steward"]
    for role_name, detector in _ROLE_DETECTORS:
        try:
            if detector():
                return role_name, _ROLE_REASON[role_name]
        except Exception:
            pass
    return None, "no role indicator found in current directory"


def build_hierarchy_lines() -> list[str]:
    """Return lines for a UML box-style inheritance diagram of all roles."""

    def _reachable(role: str) -> set[str]:
        seen: set[str] = set()
        stack = list(_ROLE_INCLUDES.get(role, ()))
        while stack:
            r = stack.pop()
            if r not in seen:
                seen.add(r)
                stack.extend(_ROLE_INCLUDES.get(r, ()))
        return seen

    root = "contributor"
    children: dict[str, list[str]] = {}
    for role in ROLES:
        if role == root:
            continue
        parents = list(_ROLE_INCLUDES.get(role, ()))
        for p in parents:
            via_others: set[str] = set()
            for o in parents:
                if o != p:
                    via_others |= {o} | _reachable(o)
            if p not in via_others:
                children.setdefault(p, []).append(role)

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


def role_components(role: str | list[str] | None) -> frozenset[str] | None:
    """Component filter for the role(s), or None (show everything)."""
    if not role:
        return None
    roles = [role] if isinstance(role, str) else role
    result: frozenset[str] = frozenset()
    for r in roles:
        own = _ROLE_COMPONENTS.get(r, frozenset())
        for parent in _ROLE_INCLUDES.get(r, ()):
            own = own | _ROLE_COMPONENTS.get(parent, frozenset())
        result = result | own
    return result or None


def role_inherits(role: str | None, parent: str) -> bool:
    """Return True if *role* equals or transitively inherits from *parent*.

    Performs a DFS traversal of ``_ROLE_INCLUDES``.  Safe against cycles.
    """
    if role is None:
        return False
    if role == parent:
        return True
    seen: set[str] = set()
    stack: list[str] = list(_ROLE_INCLUDES.get(role, ()))
    while stack:
        r = stack.pop()
        if r == parent:
            return True
        if r not in seen:
            seen.add(r)
            stack.extend(_ROLE_INCLUDES.get(r, ()))
    return False
