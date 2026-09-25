"""Assembly: import built-in role definitions and wire them into ROLE_REGISTRY."""

from .role_registry import ROLE_REGISTRY
from . import role_definitions  # noqa: F401 — registers built-in roles
