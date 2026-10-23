"""Oxigraph triple-store containerized component."""

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from .component_containerized import ContComp
from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .containerized_context import ContainerizedContext


class CompOxigraph(ContComp):
    is_external_image: bool = True

    _NEO = Namespace("http://example.org/neo4j/")
    _JEJUNE = Namespace("urn:jejune:")
    _NEO_ID = _NEO.id
    _NEO_DOCUMENT = _NEO.Document
    _NEO_LLM_MODEL_NAME = _NEO.llm_model_name
    _JEJUNE_LLM_MODEL_NAME = _JEJUNE.llm_model_name
    _ALIGNMENT_GRAPH = "urn:jejune:alignment"
    _DEFAULT_DATA_DIR = "./.jejune/oxigraph_data"
    _DEFAULT_PORT = "7878"

    @staticmethod
    def _slug(label: str) -> str:
        """Convert a normalized label to a URI-safe slug."""
        return re.sub(r"[^a-z0-9]+", "_", label).strip("_") or "cluster"

    @staticmethod
    def _cluster_uri(label: str) -> str:
        label_hash = hashlib.md5(label.encode()).hexdigest()[:8]
        return f"urn:jejune:cluster:{CompOxigraph._slug(label)}_{label_hash}"

    @staticmethod
    def _sparql_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def __init__(self, context: ContainerizedContext | None = None) -> None:
        super().__init__(
            name="oxigraph",
            image_name="oxigraph/oxigraph",
            build_context="",
            hint="run `jejune oxigraph start --help`",
            configuration=Configuration(
                ConfigurationEntry(
                    "OXIGRAPH_DATA_DIR",
                    hint="edit .jejune/env-config (default: ./.jejune/oxigraph_data)",
                    source_file=".jejune/env-config",
                    max_severity="warn",
                ),
                ConfigurationEntry(
                    "OXIGRAPH_HTTP_PORT",
                    hint="edit .jejune/env-config (default: 7878)",
                    source_file=".jejune/env-config",
                    max_severity="warn",
                ),
                ConfigurationEntry(
                    "OXIGRAPH_URI",
                    hint="edit .jejune/env-config",
                    source_file=".jejune/env-config",
                    max_severity="warn",
                ),
            ),
            context=context,
        )
        self.cli_name = self.name

    @property
    def container_name(self) -> str:
        return "jejune_oxigraph"

    def resolve_port(self, port: str | None) -> str:
        if port is not None:
            return port
        return os.environ.get("OXIGRAPH_HTTP_PORT", self._DEFAULT_PORT)

    def resolve_data_dir(self, data_dir: Path | None) -> Path:
        if data_dir is not None:
            return data_dir
        raw = os.environ.get("OXIGRAPH_DATA_DIR", self._DEFAULT_DATA_DIR)
        return Path(raw)

    def launch_container(self, data_dir: Path, port: str) -> None:
        """Start the Oxigraph container and wait for readiness."""
        data_dir.mkdir(parents=True, exist_ok=True)
        rc = self._context.docker.run_detached(
            self.container_name,
            self.image_name,
            publish=[f"{port}:7878"],
            volumes=[f"{data_dir.resolve()}:/data"],
            cmd_args=["--location", "/data", "--bind", "0.0.0.0:7878"],
        )
        if rc != 0:
            raise SystemExit(rc)
        self._wait_for_readiness(port)
        self.register(port=int(port))

    def _wait_for_readiness(self, port: str, timeout_seconds: int = 60) -> None:
        url = f"http://localhost:{port}/"
        elapsed = 0.0
        print("Waiting for Oxigraph to be ready...", end="", flush=True)
        while elapsed < timeout_seconds:
            try:
                with urllib.request.urlopen(url, timeout=3):
                    print(" ready.")
                    return
            except Exception:
                pass
            time.sleep(1.0)
            elapsed += 1.0
            print(".", end="", flush=True)
        raise RuntimeError(f"Oxigraph not ready after {timeout_seconds} seconds.")

    def _sparql_select(self, port: str, query: str) -> list[dict]:
        """Execute a SPARQL SELECT; return list of binding dicts."""
        url = f"http://localhost:{port}/query"
        req = urllib.request.Request(
            url,
            data=query.encode(),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("results", {}).get("bindings", [])

    def _sparql_update(self, port: str, update: str) -> None:
        """Execute a SPARQL UPDATE."""
        url = f"http://localhost:{port}/update"
        req = urllib.request.Request(
            url,
            data=update.encode(),
            headers={"Content-Type": "application/sparql-update"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"SPARQL UPDATE failed: {resp.status}")

    def _put_graph(self, port: str, graph_uri: str, turtle_content: bytes) -> None:
        """PUT turtle_content as a named graph via Graph Store Protocol."""
        encoded = urllib.parse.quote(graph_uri, safe=":/")
        url = f"http://localhost:{port}/store?graph={encoded}"
        req = urllib.request.Request(
            url,
            data=turtle_content,
            headers={"Content-Type": "text/turtle; charset=utf-8"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"PUT /store failed: {resp.status}")

    def _normalize_turtle(self, turtle_path: Path) -> bytes:
        """Parse, normalize labels and rename predicates, re-serialize as Turtle."""
        source = Graph()
        source.parse(str(turtle_path), format="turtle")

        document_subjects = set(source.subjects(RDF.type, self._NEO_DOCUMENT))

        normalized = Graph()
        for prefix, ns in source.namespaces():
            normalized.bind(prefix, ns)
        normalized.bind("jejune", self._JEJUNE)

        for subject, predicate, obj in source:
            if predicate == self._NEO_ID and subject not in document_subjects:
                if isinstance(obj, Literal):
                    clean = " ".join(str(obj).split()).lower()
                    obj = Literal(clean, datatype=obj.datatype)
            if predicate == self._NEO_LLM_MODEL_NAME:
                predicate = self._JEJUNE_LLM_MODEL_NAME
            normalized.add((subject, predicate, obj))

        return normalized.serialize(format="turtle").encode("utf-8")

    def list_graphs(self, port: str) -> list[str]:
        """Return all named graph URIs in the store."""
        bindings = self._sparql_select(port, "SELECT DISTINCT ?g WHERE { GRAPH ?g {} }")
        return [b["g"]["value"] for b in bindings]

    def is_store_empty(self, port: str) -> bool:
        return len(self.list_graphs(port)) == 0

    def create_store(self, port: str, turtle_path: Path) -> None:
        """Load the first graph; fails if the store already has data."""
        if not self.is_store_empty(port):
            raise RuntimeError(
                "The Oxigraph store is not empty — use `jejune oxigraph clear` first "
                "or `jejune oxigraph merge` to add another graph."
            )
        graph_uri = f"urn:jejune:graph:{turtle_path.stem}"
        self._put_graph(port, graph_uri, self._normalize_turtle(turtle_path))

    def merge_into_store(self, port: str, turtle_path: Path) -> None:
        """Load a graph into the store and update the alignment incrementally."""
        graph_uri = f"urn:jejune:graph:{turtle_path.stem}"
        self._put_graph(port, graph_uri, self._normalize_turtle(turtle_path))
        self._align_new_graph(port, graph_uri)

    def _align_new_graph(self, port: str, new_graph_uri: str) -> None:
        """Incrementally update urn:jejune:alignment for nodes in new_graph_uri."""
        q_new = f"""
        SELECT ?node ?label WHERE {{
          GRAPH <{new_graph_uri}> {{
            ?node <{self._NEO_ID}> ?label .
            FILTER NOT EXISTS {{ ?node a <{self._NEO_DOCUMENT}> }}
          }}
        }}
        """
        new_bindings = self._sparql_select(port, q_new)
        if not new_bindings:
            return

        new_node_labels: dict[str, str] = {}
        for b in new_bindings:
            new_node_labels[b["label"]["value"]] = b["node"]["value"]

        existing_clusters: dict[str, str] = {}
        for b in self._sparql_select(
            port,
            f"""
            SELECT ?label ?cluster WHERE {{
              GRAPH <{self._ALIGNMENT_GRAPH}> {{
                ?cluster a <{self._JEJUNE.LabelCluster}> .
                ?cluster <{RDFS.label}> ?label .
              }}
            }}
            """,
        ):
            existing_clusters[b["label"]["value"]] = b["cluster"]["value"]

        new_labels_needing_cluster = {
            lbl for lbl in new_node_labels if lbl not in existing_clusters
        }

        existing_matches: dict[str, list[str]] = {}
        if new_labels_needing_cluster:
            for b in self._sparql_select(
                port,
                f"""
                SELECT ?other ?label WHERE {{
                  GRAPH ?g {{
                    ?other <{self._NEO_ID}> ?label .
                    FILTER NOT EXISTS {{ ?other a <{self._NEO_DOCUMENT}> }}
                  }}
                  FILTER(?g != <{new_graph_uri}> && ?g != <{self._ALIGNMENT_GRAPH}>)
                }}
                """,
            ):
                lbl = b["label"]["value"]
                if lbl in new_labels_needing_cluster:
                    existing_matches.setdefault(lbl, []).append(b["other"]["value"])

        insert_triples: list[str] = []
        for label, node_uri in new_node_labels.items():
            escaped = self._sparql_escape(label)
            if label in existing_clusters:
                cluster_uri = existing_clusters[label]
                insert_triples.append(
                    f"<{node_uri}> <{self._JEJUNE.inLabelCluster}> <{cluster_uri}> ."
                )
            elif label in existing_matches and existing_matches[label]:
                cluster_uri = self._cluster_uri(label)
                insert_triples += [
                    f"<{cluster_uri}> a <{self._JEJUNE.LabelCluster}> .",
                    f'<{cluster_uri}> <{RDFS.label}> "{escaped}" .',
                    f"<{node_uri}> <{self._JEJUNE.inLabelCluster}> <{cluster_uri}> .",
                ]
                for other_uri in existing_matches[label]:
                    insert_triples.append(
                        f"<{other_uri}> <{self._JEJUNE.inLabelCluster}> <{cluster_uri}> ."
                    )

        if insert_triples:
            triples_block = "\n            ".join(insert_triples)
            self._sparql_update(
                port,
                f"""
                INSERT DATA {{
                  GRAPH <{self._ALIGNMENT_GRAPH}> {{
                    {triples_block}
                  }}
                }}
                """,
            )

    def _recompute_alignment(self, port: str) -> None:
        """Full recompute of urn:jejune:alignment from all per-file named graphs."""
        all_graphs = [g for g in self.list_graphs(port) if g != self._ALIGNMENT_GRAPH]
        label_to_nodes: dict[str, list[str]] = {}
        for graph_uri in all_graphs:
            for b in self._sparql_select(
                port,
                f"""
                SELECT ?node ?label WHERE {{
                  GRAPH <{graph_uri}> {{
                    ?node <{self._NEO_ID}> ?label .
                    FILTER NOT EXISTS {{ ?node a <{self._NEO_DOCUMENT}> }}
                  }}
                }}
                """,
            ):
                label_to_nodes.setdefault(b["label"]["value"], []).append(
                    b["node"]["value"]
                )

        alignment = Graph()
        alignment.bind("jejune", self._JEJUNE)
        for label, nodes in label_to_nodes.items():
            if len(nodes) < 2:
                continue
            cluster = URIRef(self._cluster_uri(label))
            alignment.add((cluster, RDF.type, self._JEJUNE.LabelCluster))
            alignment.add((cluster, RDFS.label, Literal(label)))
            for node_uri in nodes:
                alignment.add((URIRef(node_uri), self._JEJUNE.inLabelCluster, cluster))

        self._put_graph(
            port,
            self._ALIGNMENT_GRAPH,
            alignment.serialize(format="turtle").encode("utf-8"),
        )

    def clear_store(self, port: str) -> None:
        """Remove all triples from all named graphs in the store."""
        self._sparql_update(port, "DELETE WHERE { GRAPH ?g { ?s ?p ?o } }")
