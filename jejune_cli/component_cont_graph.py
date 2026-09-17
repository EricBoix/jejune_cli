"""graph containerized component."""
from pathlib import Path

import click

from .component_containerized import cont_comp
from .component_registry import ComponentRegistry
from .configuration import configuration
from .configuration_entry import configuration_entry


class comp_graph(cont_comp):
    CHUNKS_JSON = "/data/_chunks.json"
    SPLITTERS = {
        "headers":    "split_by_headers.py",
        "paragraphs": "split_by_paragraphs.py",
        "sentences":  "split_by_sentences.py",
    }

    def __init__(self) -> None:
        self._git_server = ComponentRegistry().get("git-server")
        self._neo4j      = ComponentRegistry().get("neo4j")
        self._llm        = ComponentRegistry().get("llm")
        super().__init__(
            name="graph",
            image_name="jejune:extract_knowledge_graph",
            build_context=self._git_server.remote_git_url("jejune_extract_knowledge_graph", ":DockerContext"),
            dependencies=[self._git_server, self._neo4j, self._llm],
            optional_dependencies=[ComponentRegistry().get("llm-observability")],
            configuration=configuration(
                configuration_entry("NEO4J_URI",           hint="edit .jejune/env-config",   source_file=".jejune/env-config"),
                configuration_entry("NEO4J_USERNAME",      hint="edit .jejune/env-config",   source_file=".jejune/env-config"),
                configuration_entry("NEO4J_PASSWORD",      hint="edit .jejune/env-secrets",  source_file=".jejune/env-secrets"),
                configuration_entry("LLM_MODEL_URL",       hint="edit .jejune/env-secrets",  source_file=".jejune/env-secrets"),
                configuration_entry("LLM_API_KEY",         hint="edit .jejune/env-secrets",  source_file=".jejune/env-secrets"),
                configuration_entry("LLM_MODEL_NAME",      hint="edit .jejune/env-secrets",  source_file=".jejune/env-secrets"),
                configuration_entry("TRACELOOP_BASE_URL",  hint="edit .jejune/env-config",   source_file=".jejune/env-config",  max_severity="warn"),
            ),
        )
        self.cli_name = self.name

    def dep_statuses(self) -> dict[str, tuple[bool, str]]:
        return {"neo4j": self._neo4j.is_running(), "llm": self._llm.available()}

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
            *self.docker_env_args(),
            self.image_name,
            "extract_kg_graph.py",
            "--load_json_document", self.CHUNKS_JSON,
            *extra_args,
        )
