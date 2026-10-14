"""converters containerized component — tracks all per-repo converter images in a catalog."""

import subprocess
from pathlib import Path

import click
import yaml

from .click_catalog_helpers import _docker_image_name, _has_converter
from .component_containerized import ContComp
from .containerized_context import ContainerizedContext


class CompConverters(ContComp):
    def __init__(
        self, docker_daemon, ecosystem, context: ContainerizedContext | None = None
    ) -> None:
        super().__init__(
            name="converters",
            image_name="jejune:converters",
            dependencies=[docker_daemon],
            hint="run `jejune build`",
            context=context,
        )
        self._ecosystem = ecosystem
        self.cli_name = self.name

    def _iter_local_converter_repos(self) -> list[tuple[Path, str]]:
        """Return (repo_dir, image_name) for catalog repos that are local and have a DockerContext."""
        catalog = Path.cwd() / "catalog.yaml"
        if not catalog.exists():
            return []
        try:
            docs = yaml.safe_load(catalog.read_text()).get("documents", [])
        except Exception:
            return []
        root_dir, tmp_dir = self._ecosystem.resolve_dirs()
        results: list[tuple[Path, str]] = []
        for doc in docs:
            name = doc.get("name", "")
            if not name:
                continue
            tier, base = self._ecosystem.repo_status(name, root_dir, tmp_dir)
            if tier not in ("root", "tmp"):
                continue
            repo_dir = Path(base)
            has, _, _ = _has_converter(repo_dir)
            if not has:
                continue
            results.append((repo_dir, _docker_image_name(repo_dir)))
        return results

    def _catalog_document_count(self) -> int:
        catalog = Path.cwd() / "catalog.yaml"
        if not catalog.exists():
            return 0
        try:
            docs = yaml.safe_load(catalog.read_text()).get("documents", [])
            return len(docs)
        except Exception:
            return 0

    def is_built(self) -> bool:
        repos = self._iter_local_converter_repos()
        if not repos:
            # Vacuously built only when catalog has no documents.
            # If documents exist but no repos are local, they haven't been fetched yet.
            return self._catalog_document_count() == 0
        return all(
            self._context.docker.image_exists(image_name)
            for _, image_name in repos
        )

    def build(self, no_cache: bool = False) -> None:
        repos = self._iter_local_converter_repos()
        if not repos:
            click.echo("  no local converter repos found in catalog")
            return
        extra = ["--no-cache"] if no_cache else []
        for repo_dir, image_name in repos:
            _, dockerfile, ctx = _has_converter(repo_dir)
            click.echo(f"  Building {image_name} ...")
            subprocess.run(
                [
                    "docker",
                    "build",
                    *extra,
                    "-t",
                    image_name,
                    "-f",
                    str(dockerfile),
                    str(ctx),
                ],
                check=True,
            )

    def check(self) -> tuple[str, str]:
        return "ok", ""
