"""graph containerized component."""
from .component_containerized import cont_comp
from .component_git_server import remote_git_url
from .component_registry import REGISTRY


class comp_graph(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="graph",
            image_name="jejune:extract_knowledge_graph",
            build_context=remote_git_url("jejune_extract_knowledge_graph", ":DockerContext"),
            dependencies=["git-repos-access", "neo4j", "llm"],
            optional_dependencies=["llm-observability"],
        )

    def is_running(self) -> tuple[bool, str]:
        from .graph import graph_available
        return graph_available()


graph_comp = comp_graph()
REGISTRY.add(graph_comp)
