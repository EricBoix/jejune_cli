"""converters containerized component — tracks all per-repo converter images in a catalog."""

import subprocess
from pathlib import Path

import click

from .component_catalog_file import CatalogFile
from .click_converter_helpers import _docker_image_name, _has_converter
from .component_containerized import ContComp
from .containerized_context import ContainerizedContext


class CompConverters(ContComp):
    def __init__(
        self,
        docker_daemon,
        ecosystem,
        catalog_comp,
        context: ContainerizedContext | None = None,
    ) -> None:
        super().__init__(
            name="converters",
            image_name="jejune:converters",
            dependencies=[docker_daemon],
            hint="run `jejune build`",
            context=context,
        )
        self._ecosystem = ecosystem
        self._catalog_comp = catalog_comp
        self.cli_name = self.name

    def _iter_local_converter_repos(self) -> list[tuple[Path, str]]:
        """Return (repo_dir, image_name) for catalog repos that are local and have a DockerContext."""
        catalog = CatalogFile.resolve_path()
        if not catalog.exists():
            return []
        try:
            docs = CatalogFile(catalog).raw_documents()
        except (OSError, ValueError):
            return []
        root_dir, tmp_dir = self._ecosystem.resolve_dirs()
        results: list[tuple[Path, str]] = []
        for doc in docs:
            name = doc.get("name", "")
            if not name:
                continue
            location = self._ecosystem.locate(name, root_dir, tmp_dir)
            if not location.is_local:
                continue
            repo_dir = location.local_path
            has, _, _ = _has_converter(repo_dir)
            if not has:
                continue
            results.append((repo_dir, _docker_image_name(repo_dir)))
        return results

    def _catalog_document_count(self) -> int:
        catalog = CatalogFile.resolve_path()
        if not catalog.exists():
            return 0
        try:
            return len(CatalogFile(catalog).raw_documents())
        except (OSError, ValueError):
            return 0

    def is_built(self) -> bool:
        repos = self._iter_local_converter_repos()
        if not repos:
            # Vacuously built only when catalog has no documents.
            # If documents exist but no repos are local, they haven't been fetched yet.
            return self._catalog_document_count() == 0
        return all(
            self._context.docker.image_exists(image_name) for _, image_name in repos
        )

    def build(self, no_cache: bool = False) -> None:
        docs = self._catalog_comp.load_documents(None)
        if not docs:
            click.echo("  no documents found in catalog")
            return
        root_dir, tmp_dir = self._ecosystem.resolve_dirs()
        extra = ["--no-cache"] if no_cache else []
        built_any = False
        for _name, _url, repo_dir in self._catalog_comp.iter_documents(
            docs, root_dir, tmp_dir
        ):
            has, dockerfile, ctx = _has_converter(repo_dir)
            if not has:
                continue
            image_name = _docker_image_name(repo_dir)
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
            built_any = True
        if not built_any:
            click.echo("  no converter repos found in catalog")

    def check(self) -> tuple[str, str]:
        return "ok", ""
