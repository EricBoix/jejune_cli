"""Minimal HTTP client for an Oxigraph store, plus the vocabulary simplifications share.

This package must not import anything from jejune_cli: it is meant to be extractable
as a pure Python package.
"""

import json
import urllib.request


class OxigraphStoreClient:
    NEO_ID = "http://example.org/neo4j/id"
    NEO_DOCUMENT = "http://example.org/neo4j/Document"
    RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    LLM_MODEL_NAME = "urn:jejune:llm_model_name"
    IN_LABEL_CLUSTER = "urn:jejune:inLabelCluster"
    ALIGNMENT_GRAPH = "urn:jejune:alignment"

    _TIMEOUT_SECONDS = 60

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def select(self, query: str) -> list[dict]:
        """Execute a SPARQL SELECT; return the list of binding dicts."""
        request = urllib.request.Request(
            f"{self.base_url}/query",
            data=query.encode(),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._TIMEOUT_SECONDS) as response:
            return json.loads(response.read()).get("results", {}).get("bindings", [])

    def update(self, statement: str) -> None:
        """Execute a SPARQL UPDATE."""
        request = urllib.request.Request(
            f"{self.base_url}/update",
            data=statement.encode(),
            headers={"Content-Type": "application/sparql-update"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._TIMEOUT_SECONDS) as response:
            if response.status not in (200, 204):
                raise RuntimeError(f"SPARQL UPDATE failed: {response.status}")
