"""Unit tests for ComponentRegistry: name index, deferred ordering, invalidation."""

from __future__ import annotations

import pytest

from jejune_cli.component_base import BaseComp
from jejune_cli.component_registry import ComponentRegistry, UnresolvedPlugin


class StubComp(BaseComp):
    def check(self) -> tuple[str, str]:
        return ("ok", "")


class TestComponentRegistry:
    @staticmethod
    def count_order_computations(
        registry: ComponentRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> list[int]:
        """Spy on ``_compute_order``; the returned list holds one entry per call."""
        calls: list[int] = []
        original = registry._compute_order

        def spy(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(registry, "_compute_order", spy)
        return calls

    def test_get_returns_registered_component(self) -> None:
        registry = ComponentRegistry()
        comp = StubComp("alpha")
        registry.add(comp)
        assert registry.get("alpha") is comp

    def test_get_unknown_name_returns_none(self) -> None:
        assert ComponentRegistry().get("missing") is None

    def test_get_expected_plugin_returns_unresolved_proxy(self) -> None:
        registry = ComponentRegistry()
        registry.register_expected_plugin_names({"plug"})
        proxy = registry.get("plug")
        assert isinstance(proxy, UnresolvedPlugin)
        assert proxy.name == "plug"

    def test_real_component_wins_over_expected_plugin_name(self) -> None:
        registry = ComponentRegistry()
        registry.register_expected_plugin_names({"plug"})
        comp = StubComp("plug")
        registry.add(comp)
        assert registry.get("plug") is comp

    def test_unfulfilled_plugin_names_shrinks_after_add(self) -> None:
        registry = ComponentRegistry()
        registry.register_expected_plugin_names({"plug", "other"})
        registry.add(StubComp("plug"))
        assert registry.unfulfilled_plugin_names() == {"other"}

    def test_duplicate_name_last_added_wins(self) -> None:
        registry = ComponentRegistry()
        first = StubComp("alpha")
        second = StubComp("alpha")
        registry.add(first)
        registry.add(second)
        assert registry.get("alpha") is second
        assert len(registry) == 1
        assert registry.names() == ["alpha"]

    def test_dependencies_come_before_dependents(self) -> None:
        registry = ComponentRegistry()
        base = StubComp("base")
        middle = StubComp("middle", dependencies=[base])
        top = StubComp("top", dependencies=[middle])
        for comp in (top, middle, base):
            registry.add(comp)
        assert registry.names() == ["base", "middle", "top"]

    def test_add_does_not_compute_order(self, monkeypatch) -> None:
        registry = ComponentRegistry()
        calls = self.count_order_computations(registry, monkeypatch)
        for index in range(20):
            registry.add(StubComp(f"comp{index}"))
        assert not calls

    def test_order_computed_once_for_repeated_reads(self, monkeypatch) -> None:
        registry = ComponentRegistry()
        calls = self.count_order_computations(registry, monkeypatch)
        for index in range(20):
            registry.add(StubComp(f"comp{index}"))
        registry.names()
        registry.names()
        len(registry)
        list(registry)
        assert len(calls) == 1

    def test_get_does_not_compute_order(self, monkeypatch) -> None:
        registry = ComponentRegistry()
        calls = self.count_order_computations(registry, monkeypatch)
        registry.add(StubComp("alpha"))
        registry.get("alpha")
        registry.get("missing")
        registry.unfulfilled_plugin_names()
        assert not calls

    def test_add_after_read_recomputes_order(self) -> None:
        registry = ComponentRegistry()
        late = StubComp("late")
        registry.add(StubComp("early", dependencies=[late]))
        registry.names()
        registry.add(late)
        assert registry.names() == ["late", "early"]

    def test_order_stale_until_invalidate_order(self) -> None:
        registry = ComponentRegistry()
        alpha = StubComp("alpha")
        beta = StubComp("beta")
        registry.add(alpha)
        registry.add(beta)
        assert registry.names() == ["alpha", "beta"]

        alpha.dependencies.append(beta)
        assert registry.names() == ["alpha", "beta"]

        registry.invalidate_order()
        assert registry.names() == ["beta", "alpha"]

    def test_sorted_subset_keeps_registry_order_and_appends_unknown(self) -> None:
        registry = ComponentRegistry()
        base = StubComp("base")
        top = StubComp("top", dependencies=[base])
        stranger = StubComp("stranger")
        registry.add(top)
        registry.add(base)
        assert registry.sorted_subset([top, stranger, base]) == [base, top, stranger]

    def test_sorted_active_set_follows_conditional_predicate(self) -> None:
        registry = ComponentRegistry()
        remote = StubComp("remote")
        local = StubComp("local")
        local.conditional_dependencies = [(lambda: False, remote)]
        registry.add(local)
        registry.add(remote)

        assert registry.sorted_active_set(frozenset({local})) == [local]

        local.conditional_dependencies = [(lambda: True, remote)]
        assert registry.sorted_active_set(frozenset({local})) == [remote, local]

    def test_validate_accepts_registered_dependencies(self) -> None:
        registry = ComponentRegistry()
        base = StubComp("base")
        registry.add(base)
        registry.add(StubComp("top", dependencies=[base]))
        registry.validate()

    def test_validate_rejects_unregistered_dependency_instance(self) -> None:
        registry = ComponentRegistry()
        registry.add(StubComp("top", dependencies=[StubComp("base")]))
        with pytest.raises(RuntimeError, match="unregistered instance"):
            registry.validate()

    def test_validate_skips_unresolved_plugin_dependency(self) -> None:
        registry = ComponentRegistry()
        registry.register_expected_plugin_names({"plug"})
        proxy = registry.get("plug")
        registry.add(StubComp("top", dependencies=[proxy]))
        registry.validate()
