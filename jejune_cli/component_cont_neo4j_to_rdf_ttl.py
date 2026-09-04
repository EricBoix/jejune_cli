"""neo4j-to-RDF/Turtle containerized component."""
import subprocess
from pathlib import Path

from ._env import TTL_ENV_VARS, docker_env_args
from .component_containerized import cont_comp
from .component_registry import REGISTRY


class comp_neo4j_to_rdf_ttl(cont_comp):
    def __init__(self) -> None:
        git_server = REGISTRY.get("git-server")
        super().__init__(
            name="neo4j-to-rdf-ttl",
            image_name="jejune:neo4j_to_rdf_ttl",
            build_context=git_server.remote_git_url("jejune_neo4j_to_rdf_ttl", ":DockerContext"),
            dependencies=[git_server, REGISTRY.get("docker-hub-server")],
        )

    def dump_turtle(self, output_dir: Path, filename: str) -> None:
        """Export the running Neo4j graph to output_dir/filename as RDF/Turtle."""
        result = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "host",
                "-v", f"{output_dir}:/output",
                *docker_env_args(TTL_ENV_VARS),
                self.image_name,
                "neo4j_to_rdf.py",
                f"/output/{filename}",
            ]
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)


neo4j_to_rdf_ttl_comp = comp_neo4j_to_rdf_ttl()
REGISTRY.add(neo4j_to_rdf_ttl_comp)
