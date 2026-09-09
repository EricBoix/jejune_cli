"""Doc-steward-role heuristic registrations."""
from __future__ import annotations

from pathlib import Path

from .component_registry import REGISTRY as COMP_REGISTRY
from .heuristic_step import ComponentCondition, HeuristicStep
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY
from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
from .test import _check_doc_yaml


def _graph_available() -> bool:
    ok, _ = COMP_REGISTRY.get("graph").is_running()
    return ok


def _graph_extract_command() -> str:
    neo4j_comp = COMP_REGISTRY.get("neo4j")
    cmd = "jejune graph extract"
    if not neo4j_comp.db_is_empty():
        cmd += " (warning: database is not empty)"
    return cmd


def _neo4j_running() -> bool:
    ok, _ = COMP_REGISTRY.get("neo4j").is_running()
    return ok


def _neo4j_not_empty() -> bool:
    return not COMP_REGISTRY.get("neo4j").db_is_empty()


def _neo4j_configured() -> bool:
    status, *_ = COMP_REGISTRY.get("neo4j").configuration.check()
    return status == "ok"


def _manifest_ok() -> bool:
    errors, _ = _check_doc_yaml(Path.cwd())
    return not errors


def register_heuristics() -> None:
    HEURISTIC_STEP_REGISTRY.register_precondition(
        "catalog-contributor extension installed", PLUGIN_PACKAGE_CATALOG.packages_installed
    )

    HEURISTIC_STEP_REGISTRY.register_command_precondition("jejune neo4j dump-turtle", _neo4j_running)
    HEURISTIC_STEP_REGISTRY.register_command_precondition("jejune graph split", _manifest_ok)

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Start Neo4j",
        command="jejune neo4j start --help",
        order=10,
        conditions=[ComponentCondition("neo4j"), _neo4j_configured],
        anti_conditions=[_neo4j_running],
    ), roles={"doc-steward"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Extract the knowledge graph",
        command=_graph_extract_command,
        conditions=[ComponentCondition("graph"), _graph_available],
        anti_conditions=[_neo4j_not_empty],
    ), roles={"doc-steward"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Dump the graph to Turtle",
        command="jejune neo4j dump-turtle",
        conditions=[_neo4j_running, _neo4j_not_empty],
    ), roles={"doc-steward"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Visualize the graph with neo4j UI",
        command="open http://localhost:7474 in a browser",
        conditions=[_neo4j_running, _neo4j_not_empty],
    ), roles={"doc-steward"})
