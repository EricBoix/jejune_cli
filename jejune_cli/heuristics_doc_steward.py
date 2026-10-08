"""Doc-steward-role heuristic registrations."""

from __future__ import annotations

from .component_containerized import ContComp
from .component_registry import ComponentRegistry
from .heuristic_step import ComponentCondition, HeuristicStep
from .heuristic_step_registry import HeuristicStepRegistry


def register_heuristics(
    registry: HeuristicStepRegistry,
    component_registry: ComponentRegistry,
) -> None:
    def _graph_available() -> bool:
        ok, _ = component_registry.get("graph").is_running()
        return ok

    def _graph_extract_command() -> str:
        neo4j_comp = component_registry.get("neo4j")
        cmd = "jejune graph extract"
        if not neo4j_comp.db_is_empty():
            cmd += " (warning: database is not empty)"
        return cmd

    def _neo4j_running() -> bool:
        ok, _ = component_registry.get("neo4j").is_running()
        return ok

    def _neo4j_not_empty() -> bool:
        return not component_registry.get("neo4j").db_is_empty()

    def _neo4j_configured() -> bool:
        status, *_ = component_registry.get("neo4j").configuration.check()
        return status == "ok"

    def _manifest_ok() -> bool:
        errors, _ = component_registry.get("manifest").check_manifest_referenced_files()
        return not errors

    registry.register_precondition(
        "catalog-contributor extension installed",
        component_registry.get("plugin-packages").packages_installed,
    )
    registry.register_command_precondition("jejune neo4j dump-turtle", _neo4j_running)
    registry.register_command_precondition("jejune graph split", _manifest_ok)

    registry.register(
        HeuristicStep(
            label="Start Neo4j",
            command="jejune neo4j start --help",
            order=10,
            conditions=[
                ComponentCondition("neo4j", component_registry),
                _neo4j_configured,
            ],
            anti_conditions=[_neo4j_running],
        ),
        roles={"doc-steward"},
    )

    registry.register(
        HeuristicStep(
            label="Extract the knowledge graph",
            command=_graph_extract_command,
            conditions=[
                ComponentCondition("graph", component_registry),
                _graph_available,
            ],
            anti_conditions=[_neo4j_not_empty],
        ),
        roles={"doc-steward"},
    )

    registry.register(
        HeuristicStep(
            label="Dump the graph to Turtle",
            command="jejune neo4j dump-turtle",
            conditions=[_neo4j_running, _neo4j_not_empty],
        ),
        roles={"doc-steward"},
    )

    registry.register(
        HeuristicStep(
            label="Visualize the graph with neo4j UI",
            command="open http://localhost:7474 in a browser",
            conditions=[_neo4j_running, _neo4j_not_empty],
        ),
        roles={"doc-steward"},
    )

    # One build step per non-external ContComp that has a hint: show when image is missing.
    for inst in component_registry:
        if not isinstance(inst, ContComp) or not inst.hint or inst.is_external_image:
            continue

        def _make_image_missing_check(component: ContComp):
            def _image_missing() -> bool:
                return not component.is_built()

            _image_missing.__name__ = (
                f"{component.name.replace('-', '_')}_image_missing"
            )
            return _image_missing

        registry.register(
            HeuristicStep(
                label=inst.hint,
                command=inst.hint,
                conditions=[_make_image_missing_check(inst)],
                anti_conditions=[],
            ),
            roles={"doc-steward"},
        )
