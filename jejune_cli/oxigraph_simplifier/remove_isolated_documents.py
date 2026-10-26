"""Remove document nodes that have no adjacent edge at all."""

from .node_removal import NodeRemoval
from .simplification import Simplification, SimplificationReport
from .store_client import OxigraphStoreClient


class RemoveIsolatedDocuments(Simplification):
    """A document node is isolated when it is neither subject nor object of any edge
    (rdf:type and literal properties are not edges)."""

    name = "remove-isolated-documents"
    description = "Remove document nodes without any adjacent edge."

    def run(
        self, store_client: OxigraphStoreClient, dry_run: bool
    ) -> SimplificationReport:
        isolated_documents = self._fetch_isolated_documents(store_client)
        if isolated_documents and not dry_run:
            store_client.update(NodeRemoval.build_update(isolated_documents))
        return SimplificationReport(
            name=self.name,
            examined=len(isolated_documents),
            nodes_removed=len(isolated_documents),
        )

    def _fetch_isolated_documents(self, store_client: OxigraphStoreClient) -> list[str]:
        outgoing_edge = NodeRemoval.edge_pattern("?node", "?out_p", "?out_o", "?out_g")
        incoming_edge = NodeRemoval.edge_pattern("?in_s", "?in_p", "?node", "?in_g")
        bindings = store_client.select(f"""
            SELECT DISTINCT ?node WHERE {{
              GRAPH ?type_graph {{ ?node <{store_client.RDF_TYPE}> <{store_client.NEO_DOCUMENT}> }}
              FILTER(isIRI(?node))
              FILTER NOT EXISTS {{ {outgoing_edge} }}
              FILTER NOT EXISTS {{ {incoming_edge} }}
            }}
            """)
        return [binding["node"]["value"] for binding in bindings]
