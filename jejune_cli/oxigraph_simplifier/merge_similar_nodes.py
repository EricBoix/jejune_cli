"""Merge nodes related by urn:jejune:similarTo that are really the same entity."""

from dataclasses import dataclass

from .simplification import Simplification, SimplificationReport
from .store_client import OxigraphStoreClient


@dataclass(frozen=True)
class NodeIdentity:
    """What identifies a node across all graphs: its ids, rdf:types and model names."""

    identifiers: frozenset[str]
    types: frozenset[str]
    model_names: frozenset[str]


class MergeSimilarNodes(Simplification):
    """Merge the two ends of a similarTo edge when their id is identical and the
    rdf:type set of one is included in the rdf:type set of the other.

    similarTo is not stored: it is derived from nodes sharing an inLabelCluster in the
    alignment graph. rdf:type is multi-valued ("Material, __Entity__" is the two types
    "Material" and "__Entity__"); both nodes must have at least one type. The surviving
    node is the one with the longest type list, so no type list is ever invented. A
    node that fits several incomparable supersets goes to the one with the most
    distinct llm_model_name values. The surviving node receives every triple of the
    merged nodes in every graph, so all adjacent edges and all llm_model_name values
    (one literal triple per distinct model name) are preserved. The dropped nodes leave
    the alignment graph, which discards the similarTo edges between them.
    """

    name = "merge-similar"
    description = (
        "Merge similarTo nodes having identical id and rdf:type sets related by "
        "inclusion."
    )

    def run(
        self, store_client: OxigraphStoreClient, dry_run: bool
    ) -> SimplificationReport:
        similar_pairs = self._fetch_similar_pairs(store_client)
        node_identities = self._fetch_node_identities(store_client, similar_pairs)
        dropped_to_survivor = self._resolve_survivors(similar_pairs, node_identities)
        report = SimplificationReport(
            name=self.name,
            examined=len(similar_pairs),
            nodes_removed=len(dropped_to_survivor),
            self_loops_created=self._count_self_loops_created(
                store_client, dropped_to_survivor
            ),
        )
        if dropped_to_survivor and not dry_run:
            store_client.update(self._build_update(dropped_to_survivor))
        return report

    def _fetch_similar_pairs(
        self, store_client: OxigraphStoreClient
    ) -> list[tuple[str, str]]:
        bindings = store_client.select(f"""
            SELECT DISTINCT ?node_a ?node_b WHERE {{
              GRAPH <{store_client.ALIGNMENT_GRAPH}> {{
                ?node_a <{store_client.IN_LABEL_CLUSTER}> ?cluster .
                ?node_b <{store_client.IN_LABEL_CLUSTER}> ?cluster .
                FILTER(?node_a != ?node_b && STR(?node_a) < STR(?node_b))
              }}
            }}
            """)
        return [
            (binding["node_a"]["value"], binding["node_b"]["value"])
            for binding in bindings
        ]

    def _fetch_node_identities(
        self, store_client: OxigraphStoreClient, similar_pairs: list[tuple[str, str]]
    ) -> dict[str, NodeIdentity]:
        """Map each node to its ids, rdf:types and llm_model_names across all graphs."""
        nodes = sorted({node for pair in similar_pairs for node in pair})
        if not nodes:
            return {}
        values = " ".join(f"<{node}>" for node in nodes)
        bindings = store_client.select(f"""
            SELECT ?node ?identifier ?type ?model_name WHERE {{
              VALUES ?node {{ {values} }}
              OPTIONAL {{ GRAPH ?id_graph {{ ?node <{store_client.NEO_ID}> ?identifier }} }}
              OPTIONAL {{ GRAPH ?type_graph {{ ?node <{store_client.RDF_TYPE}> ?type }} }}
              OPTIONAL {{ GRAPH ?model_graph {{ ?node <{store_client.LLM_MODEL_NAME}> ?model_name }} }}
            }}
            """)
        identifiers: dict[str, set[str]] = {node: set() for node in nodes}
        types: dict[str, set[str]] = {node: set() for node in nodes}
        model_names: dict[str, set[str]] = {node: set() for node in nodes}
        for binding in bindings:
            node = binding["node"]["value"]
            if "identifier" in binding:
                identifiers[node].add(binding["identifier"]["value"])
            if "type" in binding:
                types[node].add(binding["type"]["value"])
            if "model_name" in binding:
                model_names[node].add(binding["model_name"]["value"])
        return {
            node: NodeIdentity(
                identifiers=frozenset(identifiers[node]),
                types=frozenset(types[node]),
                model_names=frozenset(model_names[node]),
            )
            for node in nodes
        }

    def _have_same_identity(
        self, identity_a: NodeIdentity, identity_b: NodeIdentity
    ) -> bool:
        """Same id, and both typed with one type set included in the other."""
        return (
            bool(identity_a.identifiers)
            and identity_a.identifiers == identity_b.identifiers
            and bool(identity_a.types)
            and bool(identity_b.types)
            and (
                identity_a.types <= identity_b.types
                or identity_b.types <= identity_a.types
            )
        )

    def _resolve_survivors(
        self,
        similar_pairs: list[tuple[str, str]],
        node_identities: dict[str, NodeIdentity],
    ) -> dict[str, str]:
        """Merge nodes sequentially, always judging the current survivors.

        Phase 1 merges nodes with equal type sets (smallest URI survives). Phase 2 merges
        each node into a similar survivor with a strictly larger type set, choosing the
        one with the most distinct llm_model_names (then the longest type list, then the
        smallest URI). Smaller type sets go first so that chains A<B<C collapse upward.
        A survivor always keeps its own type set: incomparable nodes never get merged
        through a common subset. Returns dropped -> final survivor.
        """
        dropped_to_survivor: dict[str, str] = {}
        partners: dict[str, set[str]] = {node: set() for node in node_identities}
        model_names: dict[str, set[str]] = {
            node: set(identity.model_names)
            for node, identity in node_identities.items()
        }
        for node_a, node_b in similar_pairs:
            partners[node_a].add(node_b)
            partners[node_b].add(node_a)

        def find_survivor(node: str) -> str:
            while node in dropped_to_survivor:
                node = dropped_to_survivor[node]
            return node

        def merge(dropped: str, survivor: str) -> None:
            dropped_to_survivor[dropped] = survivor
            model_names[survivor] |= model_names[dropped]
            partners[survivor] |= partners[dropped]

        for node_a, node_b in similar_pairs:
            survivor_a = find_survivor(node_a)
            survivor_b = find_survivor(node_b)
            identity_a = node_identities[survivor_a]
            identity_b = node_identities[survivor_b]
            if (
                survivor_a != survivor_b
                and identity_a.types == identity_b.types
                and self._have_same_identity(identity_a, identity_b)
            ):
                merge(max(survivor_a, survivor_b), min(survivor_a, survivor_b))

        for node in sorted(
            node_identities, key=lambda name: (len(node_identities[name].types), name)
        ):
            if node in dropped_to_survivor:
                continue
            identity = node_identities[node]
            candidates = [
                candidate
                for candidate in {find_survivor(partner) for partner in partners[node]}
                if candidate != node
                and self._have_same_identity(identity, node_identities[candidate])
                and identity.types < node_identities[candidate].types
            ]
            if candidates:
                target = min(
                    candidates,
                    key=lambda candidate: (
                        -len(model_names[candidate]),
                        -len(node_identities[candidate].types),
                        candidate,
                    ),
                )
                merge(node, target)

        return {node: find_survivor(node) for node in dropped_to_survivor}

    def _count_self_loops_created(
        self, store_client: OxigraphStoreClient, dropped_to_survivor: dict[str, str]
    ) -> int:
        """Count distinct (survivor, predicate) self-loops that the merge creates.

        An edge between two nodes of the same merge group becomes a self-loop on the
        survivor. Self-loops the survivor already has are not counted.
        """
        if not dropped_to_survivor:
            return 0
        survivors = set(dropped_to_survivor.values())
        member_to_survivor = {survivor: survivor for survivor in survivors}
        member_to_survivor.update(dropped_to_survivor)
        member_values = " ".join(
            f"(<{member}> <{survivor}>)"
            for member, survivor in member_to_survivor.items()
        )
        bindings = store_client.select(f"""
            SELECT DISTINCT ?survivor ?predicate WHERE {{
              VALUES (?subject ?survivor) {{ {member_values} }}
              VALUES (?object ?object_survivor) {{ {member_values} }}
              GRAPH ?graph {{ ?subject ?predicate ?object }}
              FILTER(?graph != <{store_client.ALIGNMENT_GRAPH}>
                     && ?subject != ?object
                     && ?survivor = ?object_survivor)
              FILTER NOT EXISTS {{ GRAPH ?other_graph {{ ?survivor ?predicate ?survivor }} }}
            }}
            """)
        return len(bindings)

    def _build_update(self, dropped_to_survivor: dict[str, str]) -> str:
        """Move every triple of each dropped node to its survivor, then unalign it."""
        alignment_graph = OxigraphStoreClient.ALIGNMENT_GRAPH
        in_label_cluster = OxigraphStoreClient.IN_LABEL_CLUSTER
        operations: list[str] = []
        for dropped, survivor in sorted(dropped_to_survivor.items()):
            operations.append(f"""
                DELETE {{ GRAPH ?graph {{ <{dropped}> ?predicate ?object }} }}
                INSERT {{ GRAPH ?graph {{ <{survivor}> ?predicate ?object }} }}
                WHERE {{
                  GRAPH ?graph {{ <{dropped}> ?predicate ?object }}
                  FILTER(?graph != <{alignment_graph}>)
                }}""")
            operations.append(f"""
                DELETE {{ GRAPH ?graph {{ ?subject ?predicate <{dropped}> }} }}
                INSERT {{ GRAPH ?graph {{ ?subject ?predicate <{survivor}> }} }}
                WHERE {{
                  GRAPH ?graph {{ ?subject ?predicate <{dropped}> }}
                  FILTER(?graph != <{alignment_graph}>)
                }}""")
            operations.append(f"""
                DELETE WHERE {{
                  GRAPH <{alignment_graph}> {{ <{dropped}> <{in_label_cluster}> ?cluster }}
                }}""")
        return " ;\n".join(operations)
