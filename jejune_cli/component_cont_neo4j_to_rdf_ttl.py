"""neo4j-to-RDF/Turtle containerized component."""
import subprocess
from pathlib import Path

from .component_containerized import cont_comp
from .component_registry import ComponentRegistry
from .configuration import configuration
from .configuration_entry import configuration_entry


class comp_neo4j_to_rdf_ttl(cont_comp):
    def __init__(self) -> None:
        git_server = ComponentRegistry().get("git-server")
        super().__init__(
            name="neo4j-to-rdf-ttl",
            image_name="jejune:neo4j_to_rdf_ttl",
            build_context=git_server.remote_git_url("jejune_neo4j_to_rdf_ttl", ":DockerContext"),
            dependencies=[git_server, ComponentRegistry().get("docker-hub-server")],
            configuration=configuration(
                configuration_entry("NEO4J_URI",      hint="edit .jejune/env-config",   source_file=".jejune/env-config"),
                configuration_entry("NEO4J_USERNAME", hint="edit .jejune/env-config",   source_file=".jejune/env-config"),
                configuration_entry("NEO4J_PASSWORD", hint="edit .jejune/env-secrets",  source_file=".jejune/env-secrets"),
            ),
        )

    def dump_turtle(self, output_dir: Path, filename: str) -> None:
        """Export the running Neo4j graph to output_dir/filename as RDF/Turtle."""
        result = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "host",
                "-v", f"{output_dir}:/output",
                *self.docker_env_args(),
                self.image_name,
                "neo4j_to_rdf.py",
                f"/output/{filename}",
            ]
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)
