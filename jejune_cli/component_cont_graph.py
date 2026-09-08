"""graph containerized component."""
from pathlib import Path

import click

from .component_containerized import cont_comp
from .component_registry import ComponentRegistry


class comp_graph(cont_comp):
    CHUNKS_JSON = "/data/_chunks.json"
    SPLITTERS = {
        "headers":    "split_by_headers.py",
        "paragraphs": "split_by_paragraphs.py",
        "sentences":  "split_by_sentences.py",
    }

    def __init__(self) -> None:
        git_server = ComponentRegistry().get("git-server")
        super().__init__(
            name="graph",
            image_name="jejune:extract_knowledge_graph",
            build_context=git_server.remote_git_url("jejune_extract_knowledge_graph", ":DockerContext"),
            dependencies=[git_server, ComponentRegistry().get("neo4j"), ComponentRegistry().get("llm")],
            optional_dependencies=[ComponentRegistry().get("llm-observability")],
        )

    def dep_statuses(self) -> dict[str, tuple[bool, str]]:
        from .llm import llm_available
        neo4j = next(d for d in self.dependencies if d.name == "neo4j")
        return {"neo4j": neo4j.is_running(), "llm": llm_available()}

    def is_running(self) -> tuple[bool, str]:
        statuses = self.dep_statuses()
        if all(ok for ok, _ in statuses.values()):
            return True, "ok"
        return False, "; ".join(
            f"{dep}: {msg}" for dep, (ok, msg) in statuses.items() if not ok
        )

    def preflight(self) -> None:
        for dep, (ok, msg) in self.dep_statuses().items():
            if not ok:
                raise click.ClickException(
                    f"{dep} is not available ({msg}) — refer to `jejune {dep} status`"
                )

    def run_split(
        self,
        doc_dir: str | Path,
        splitter: str,
        output: str | None,
        no_cache: bool,
        extra_args: tuple,
    ) -> None:
        doc_dir = Path(doc_dir).resolve()
        self.build(no_cache)
        output_args = ("--output", output) if output is not None else ()
        click.echo(f"Splitting with {self.SPLITTERS[splitter]} ...")
        self._run(
            "docker", "run", "--rm", "--tty",
            "--network", "host",
            "-v", f"{doc_dir}:/data",
            "--name", "jejune_split",
            self.image_name,
            self.SPLITTERS[splitter],
            "--catalog", "/data/manifest.yaml",
            *output_args,
            *extra_args,
        )

    def run_extract(
        self,
        doc_dir: str | Path,
        no_cache: bool,
        extra_args: tuple,
    ) -> None:
        from ._env import EXTRACT_ENV_VARS, docker_env_args
        doc_dir = Path(doc_dir).resolve()
        self.build(no_cache)
        docker_run = (
            "docker", "run", "--rm", "--tty",
            "--network", "host",
            "-v", f"{doc_dir}:/data",
        )
        click.echo("Splitting document into chunks ...")
        self._run(
            *docker_run,
            "--name", "jejune_split",
            self.image_name,
            self.SPLITTERS["headers"],
            "--catalog", "/data/manifest.yaml",
            "--output", self.CHUNKS_JSON,
        )
        click.echo("Running extraction ...")
        self._run(
            *docker_run,
            "--name", "jejune_extract_knowledge_graph",
            *docker_env_args(EXTRACT_ENV_VARS),
            self.image_name,
            "extract_kg_graph.py",
            "--load_json_document", self.CHUNKS_JSON,
            *extra_args,
        )
