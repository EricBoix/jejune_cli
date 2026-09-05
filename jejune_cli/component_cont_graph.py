"""graph containerized component."""
from .component_containerized import cont_comp


class comp_graph(cont_comp):
    def __init__(self) -> None:
        git_server = type(self).registry.get("git-server")
        super().__init__(
            name="graph",
            image_name="jejune:extract_knowledge_graph",
            build_context=git_server.remote_git_url("jejune_extract_knowledge_graph", ":DockerContext"),
            dependencies=[git_server, type(self).registry.get("neo4j"), type(self).registry.get("llm")],
            optional_dependencies=[type(self).registry.get("llm-observability")],
        )
        type(self).registry.add(self)

    def is_running(self) -> tuple[bool, str]:
        from .graph import graph_available
        return graph_available()


graph_comp = comp_graph()
