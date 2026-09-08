"""Doc-steward-role heuristic registrations."""
from __future__ import annotations

from .extensions_registry import _extensions_installed
from .heuristic_step import HeuristicStep
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY


def _graph_available() -> bool:
    from .component_registry import REGISTRY as COMP_REGISTRY
    ok, _ = COMP_REGISTRY.get("graph").is_running()
    return ok


def _graph_extract_command() -> str:
    from .component_registry import REGISTRY as COMP_REGISTRY
    neo4j_comp = COMP_REGISTRY.get("neo4j")
    cmd = "jejune graph extract"
    if not neo4j_comp.db_is_empty():
        cmd += " (warning: database is not empty)"
    return cmd


def _neo4j_running() -> bool:
    from .component_registry import REGISTRY as COMP_REGISTRY
    neo4j_comp = COMP_REGISTRY.get("neo4j")
    ok, _ = neo4j_comp.is_running()
    return ok


def _neo4j_not_empty() -> bool:
    from .component_registry import REGISTRY as COMP_REGISTRY
    neo4j_comp = COMP_REGISTRY.get("neo4j")
    return not neo4j_comp.db_is_empty()


def _neo4j_configured() -> bool:
    from .component_registry import REGISTRY as COMP_REGISTRY
    neo4j_comp = COMP_REGISTRY.get("neo4j")
    status, *_ = neo4j_comp.configuration.check()
    return status == "ok"


def _manifest_ok() -> bool:
    from pathlib import Path
    from .test import _check_doc_yaml
    errors, _ = _check_doc_yaml(Path.cwd())
    return not errors


def register_heuristics() -> None:
    from .heuristic_step import ComponentCondition

    HEURISTIC_STEP_REGISTRY.register_precondition("catalog-contributor extension installed", _extensions_installed)

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
