"""Run simplifications against an Oxigraph store."""

from .merge_similar_nodes import MergeSimilarNodes
from .remove_isolated_documents import RemoveIsolatedDocuments
from .remove_isolated_edges import RemoveIsolatedEdges
from .simplification import Simplification, SimplificationReport
from .store_client import OxigraphStoreClient


class OxigraphSimplifier:
    # Ordered (merging can change node degrees, hence goes first). The only place to edit to register a new simplification.
    AVAILABLE_SIMPLIFICATIONS: tuple[type[Simplification], ...] = (
        MergeSimilarNodes,
        RemoveIsolatedEdges,
        RemoveIsolatedDocuments,
    )

    def __init__(self, base_url: str) -> None:
        self._store_client = OxigraphStoreClient(base_url)

    @classmethod
    def available_names(cls) -> list[str]:
        return [simplification.name for simplification in cls.AVAILABLE_SIMPLIFICATIONS]

    @classmethod
    def describe(cls) -> dict[str, str]:
        return {
            simplification.name: simplification.description
            for simplification in cls.AVAILABLE_SIMPLIFICATIONS
        }

    def simplify(
        self, selected_names: list[str] | None = None, dry_run: bool = False
    ) -> list[SimplificationReport]:
        """Run the selected simplifications (default: all) in registration order."""
        unknown_names = set(selected_names or []) - set(self.available_names())
        if unknown_names:
            raise ValueError(f"Unknown simplification(s): {sorted(unknown_names)}")
        return [
            simplification().run(self._store_client, dry_run)
            for simplification in self.AVAILABLE_SIMPLIFICATIONS
            if not selected_names or simplification.name in selected_names
        ]
