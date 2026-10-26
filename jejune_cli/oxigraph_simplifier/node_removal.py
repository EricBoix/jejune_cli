"""Shared by simplifications that delete nodes outright."""

from .store_client import OxigraphStoreClient


class NodeRemoval:
    @staticmethod
    def build_update(nodes: list[str]) -> str:
        """Delete every triple having one of the nodes as subject or object, in all
        graphs (the alignment graph included, which drops their similarTo edges)."""
        values = " ".join(f"<{node}>" for node in sorted(nodes))
        return f"""
            DELETE {{ GRAPH ?graph {{ ?node ?predicate ?object }} }}
            WHERE {{ VALUES ?node {{ {values} }} GRAPH ?graph {{ ?node ?predicate ?object }} }} ;
            DELETE {{ GRAPH ?graph {{ ?subject ?predicate ?node }} }}
            WHERE {{ VALUES ?node {{ {values} }} GRAPH ?graph {{ ?subject ?predicate ?node }} }}
            """

    @staticmethod
    def edge_pattern(subject: str, predicate: str, obj: str, graph: str) -> str:
        """SPARQL fragment matching an edge: a non rdf:type triple between two
        resources, outside the alignment graph (whose triples are not edges)."""
        return f"""GRAPH {graph} {{ {subject} {predicate} {obj} }}
              FILTER(isIRI({obj}) && {predicate} != <{OxigraphStoreClient.RDF_TYPE}>
                     && {graph} != <{OxigraphStoreClient.ALIGNMENT_GRAPH}>)"""
