"""Remove document/non-document edges standing alone, with both their end nodes."""

from .node_removal import NodeRemoval
from .simplification import Simplification, SimplificationReport
from .store_client import OxigraphStoreClient


class RemoveIsolatedEdges(Simplification):
    """An edge is isolated when neither its subject nor its object has any other
    adjacent edge. It is removed, with both nodes, only when exactly one of the two
    nodes is of document type."""

    name = "remove-isolated-edges"
    description = (
        "Remove isolated edges (and their nodes) joining a document to a non-document."
    )

    def run(
        self, store_client: OxigraphStoreClient, dry_run: bool
    ) -> SimplificationReport:
        isolated_edges = self._fetch_isolated_edges(store_client)
        nodes = [node for edge in isolated_edges for node in edge]
        if nodes and not dry_run:
            store_client.update(NodeRemoval.build_update(nodes))
        return SimplificationReport(
            name=self.name,
            examined=len(isolated_edges),
            nodes_removed=len(nodes),
            edges_removed=len(isolated_edges),
        )

    def _fetch_isolated_edges(
        self, store_client: OxigraphStoreClient
    ) -> list[tuple[str, str]]:
        document_type = f"<{store_client.RDF_TYPE}> <{store_client.NEO_DOCUMENT}>"
        edge = NodeRemoval.edge_pattern("?subject", "?predicate", "?object", "?graph")
        subject_other_out = NodeRemoval.edge_pattern(
            "?subject", "?s_out_p", "?s_out_o", "?s_out_g"
        )
        object_other_out = NodeRemoval.edge_pattern(
            "?object", "?o_out_p", "?o_out_o", "?o_out_g"
        )
        subject_any_in = NodeRemoval.edge_pattern(
            "?s_in_s", "?s_in_p", "?subject", "?s_in_g"
        )
        object_other_in = NodeRemoval.edge_pattern(
            "?o_in_s", "?o_in_p", "?object", "?o_in_g"
        )
        bindings = store_client.select(f"""
            SELECT DISTINCT ?subject ?object WHERE {{
              {edge}
              FILTER(isIRI(?subject) && ?subject != ?object)
              BIND(EXISTS {{ GRAPH ?subject_type_graph {{ ?subject {document_type} }} }}
                   AS ?subject_is_document)
              BIND(EXISTS {{ GRAPH ?object_type_graph {{ ?object {document_type} }} }}
                   AS ?object_is_document)
              FILTER(?subject_is_document != ?object_is_document)
              FILTER NOT EXISTS {{ {subject_other_out}
                                   FILTER(!(?s_out_p = ?predicate && ?s_out_o = ?object)) }}
              FILTER NOT EXISTS {{ {subject_any_in} }}
              FILTER NOT EXISTS {{ {object_other_out} }}
              FILTER NOT EXISTS {{ {object_other_in}
                                   FILTER(!(?o_in_s = ?subject && ?o_in_p = ?predicate)) }}
            }}
            """)
        return [
            (binding["subject"]["value"], binding["object"]["value"])
            for binding in bindings
        ]
