"""Deployer extension precondition registration."""
from .extensions_registry import _ROLE_PACKAGES, _extensions_installed, _do_extensions_install
from .next_steps import register_precondition

# Re-exported for callers that reference the deployer package list directly.
_DEPLOYER_CHECK_PACKAGES: list[tuple[str, str, str]] = _ROLE_PACKAGES["deployer"]
_PLUGIN_NAMES: frozenset[str] = frozenset(t[2] for t in _DEPLOYER_CHECK_PACKAGES)

register_precondition("deployer extensions installed", _extensions_installed)

__all__ = [
    "_DEPLOYER_CHECK_PACKAGES",
    "_PLUGIN_NAMES",
    "_extensions_installed",
    "_do_extensions_install",
]
