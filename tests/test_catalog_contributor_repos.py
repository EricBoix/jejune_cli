from types import SimpleNamespace

import pytest

from jejune_cli.component_catalog import CompCatalog
from jejune_cli.component_ecosystem import CompEcosystem
from jejune_cli.role import Role
from jejune_cli.role_registry import RoleRegistry


@pytest.fixture
def role_registry(monkeypatch):
    registry = RoleRegistry(SimpleNamespace(get=lambda name: None))
    registry.register(
        Role(
            name="deployment-catalog",
            component_names=("catalog",),
            includes=(),
            section_title="",
            is_abstract=True,
        )
    )
    registry.register(
        Role(
            name="catalog-contributor",
            component_names=("catalog",),
            includes=("deployment-catalog",),
            section_title="",
        )
    )
    registry.register(
        Role(
            name="deployer",
            component_names=("catalog",),
            includes=(),
            section_title="",
        )
    )
    return registry


@pytest.fixture
def catalog(role_registry):
    return CompCatalog(
        SimpleNamespace(name="ecosystem"),
        SimpleNamespace(name="git-access"),
        role_registry,
        SimpleNamespace(register_repo_name=lambda *arguments: None),
    )


@pytest.fixture
def ecosystem(role_registry):
    return CompEcosystem(
        SimpleNamespace(name="git-server"),
        SimpleNamespace(name="git-access"),
        role_registry,
        SimpleNamespace(),
    )


def test_catalog_contributor_does_not_register_catalog_repo(catalog, monkeypatch):
    monkeypatch.setenv("JEJUNE_ROLE", "catalog-contributor")
    assert catalog.repos == []


def test_other_roles_register_catalog_repo(catalog, monkeypatch):
    monkeypatch.setenv("JEJUNE_ROLE", "deployer")
    assert catalog.repos == [(None, None)]


def test_catalog_contributor_needs_remote_without_component_repos(
    ecosystem, monkeypatch
):
    monkeypatch.setenv("JEJUNE_ROLE", "catalog-contributor")
    assert ecosystem.ecosystem_needs_remote() is True
