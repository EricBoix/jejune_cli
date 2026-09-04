"""Doc-steward extension precondition registration."""
from .extensions_registry import _extensions_installed
from .next_steps import register_precondition

register_precondition("catalog-contributor extension installed", _extensions_installed)
