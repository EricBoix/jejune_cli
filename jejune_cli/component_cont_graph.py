"""graph containerized component."""
from .component_containerized import cont_comp
from .component_registry import ComponentRegistry


class comp_graph(cont_comp):
    def __init__(self) -> None:
        git_server = ComponentRegistry().get("git-server")
        super().__init__(
            name="graph",
            image_name="jejune:extract_knowledge_graph",
            build_context=git_server.remote_git_url("jejune_extract_knowledge_graph", ":DockerContext"),
            dependencies=[git_server, ComponentRegistry().get("neo4j"), ComponentRegistry().get("llm")],
            optional_dependencies=[ComponentRegistry().get("llm-observability")],
        )

    def is_running(self) -> tuple[bool, str]:
        from .graph import graph_available
        return graph_available()


