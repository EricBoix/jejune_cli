"""Unit tests for RoleRegistry.build_hierarchy_lines root derivation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from jejune_cli.core.component_registry import ComponentRegistry
from jejune_cli.roles.role import Role
from jejune_cli.roles.role_definitions import wire_roles
from jejune_cli.roles.role_registry import RoleRegistry


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


class TestDeployerRole:
    DEPLOYER_UI_COMPONENT_NAMES = ("docs-server", "kg-viewer", "md-browser", "hub")

    @staticmethod
    def deployer_component_names() -> tuple[str, ...]:
        registry = RoleRegistry(ComponentRegistry())
        wire_roles(registry)
        deployer = registry.get("deployer")
        assert deployer is not None
        return deployer.component_names

    def test_hub_is_registered_to_deployer_role(self) -> None:
        assert "hub" in self.deployer_component_names()

    @pytest.mark.parametrize("component_name", DEPLOYER_UI_COMPONENT_NAMES)
    def test_every_ui_component_is_registered_to_deployer_role(
        self, component_name: str
    ) -> None:
        assert component_name in self.deployer_component_names()


class TestRoleVisibleCliCommands:
    """Invocation gating: a role may only invoke commands of itself and inherited roles."""

    @staticmethod
    def make_registry() -> RoleRegistry:
        known_component_names = {
            "convert",
            "converters",
            "ecosystem",
            "catalog",
            "manifest",
        }
        component_registry = SimpleNamespace(
            get=lambda name: (
                SimpleNamespace(cli_name=name)
                if name in known_component_names
                else None
            )
        )
        registry = RoleRegistry(component_registry)
        wire_roles(registry)
        return registry

    def test_catalog_contributor_cannot_invoke_convert(self) -> None:
        registry = self.make_registry()
        role = registry.get("catalog-contributor")
        assert "convert" not in registry.role_visible_cli_commands(role)
        assert "manifest" not in registry.role_visible_cli_commands(role)

    def test_catalog_contributor_invokes_inherited_and_own_commands(self) -> None:
        registry = self.make_registry()
        visible = registry.role_visible_cli_commands(
            registry.get("catalog-contributor")
        )
        assert {"converters", "catalog", "ecosystem", "git-access"} <= visible

    def test_doc_steward_cannot_invoke_converters(self) -> None:
        registry = self.make_registry()
        visible = registry.role_visible_cli_commands(registry.get("doc-steward"))
        assert "converters" not in visible
        assert {"convert", "manifest", "ecosystem"} <= visible

    def test_convert_is_offered_by_doc_steward_only(self) -> None:
        registry = self.make_registry()
        assert registry.is_role_owned_cli_command("convert")
        assert registry.roles_offering_cli_command("convert") == ["doc-steward"]

    def test_unowned_command_is_infrastructure(self) -> None:
        assert not self.make_registry().is_role_owned_cli_command("document")

    def test_help_shows_inherited_non_abstract_roles_only(self) -> None:
        registry = self.make_registry()
        shown_names = [
            role.name
            for role in registry.display_roles_shown_to(
                registry.get("catalog-contributor")
            )
        ]
        assert "catalog-contributor" in shown_names
        assert "contributor" in shown_names
        assert "deployment-catalog" not in shown_names
        assert "doc-steward" not in shown_names

    def test_help_shows_every_display_role_when_no_role_is_active(self) -> None:
        registry = self.make_registry()
        assert registry.display_roles_shown_to(Role.NONE) == registry.display_roles
