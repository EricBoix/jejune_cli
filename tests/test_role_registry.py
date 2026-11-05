"""Unit tests for RoleRegistry.build_hierarchy_lines root derivation."""

from __future__ import annotations

import pytest

from jejune_cli.component_registry import ComponentRegistry
from jejune_cli.role import Role
from jejune_cli.role_registry import RoleRegistry


class TestBuildHierarchyLines:
    @staticmethod
    def make_role(name: str, includes: tuple[str, ...] = ()) -> Role:
        return Role(
            name=name, component_names=(), includes=includes, section_title=name
        )

    @staticmethod
    def make_registry(*roles: Role) -> RoleRegistry:
        registry = RoleRegistry(ComponentRegistry())
        for role in roles:
            registry.register(role)
        return registry

    def test_root_is_derived_not_hardcoded(self) -> None:
        registry = self.make_registry(
            self.make_role("base"),
            self.make_role("child", includes=("base",)),
        )
        lines = registry.build_hierarchy_lines()
        assert any("base" in line for line in lines)
        assert any("child" in line for line in lines)

    def test_no_parentless_role_raises(self) -> None:
        registry = self.make_registry(
            self.make_role("first", includes=("second",)),
            self.make_role("second", includes=("first",)),
        )
        with pytest.raises(ValueError, match="exactly one root"):
            registry.build_hierarchy_lines()

    def test_multiple_parentless_roles_raise(self) -> None:
        registry = self.make_registry(
            self.make_role("first"),
            self.make_role("second"),
        )
        with pytest.raises(ValueError, match="exactly one root"):
            registry.build_hierarchy_lines()
