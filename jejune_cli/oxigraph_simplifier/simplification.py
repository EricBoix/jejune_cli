"""Base class of every store simplification, and the report each one returns."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .store_client import OxigraphStoreClient


@dataclass
class SimplificationReport:
    name: str
    examined: int = 0
    nodes_removed: int = 0
    edges_removed: int = 0
    self_loops_created: int = 0


class Simplification(ABC):
    """One way of simplifying the knowledge graph held in an Oxigraph store.

    To add a simplification: subclass this in its own module, then append the class
    to OxigraphSimplifier.AVAILABLE_SIMPLIFICATIONS.
    """

    name: str
    description: str

    @abstractmethod
    def run(
        self, store_client: OxigraphStoreClient, dry_run: bool
    ) -> SimplificationReport:
        """Simplify the store (or only report what would change when dry_run)."""
