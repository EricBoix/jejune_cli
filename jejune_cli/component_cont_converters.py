"""converters containerized component — tracks all per-repo converter images in a catalog."""

import subprocess
from pathlib import Path

import click

from .component_catalog_file import CatalogFile
from .component_containerized import ContComp
from .containerized_context import ContainerizedContext


class CompConverters(ContComp):
    DOC_PREFIX = "jejune_doc_"

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
        directories = self._ecosystem.resolve_dirs()
        results: list[tuple[Path, str]] = []
        for doc in docs:
            name = doc.get("name", "")
            if not name:
                continue
            location = self._ecosystem.locate(name, directories)
            if not location.is_local:
                continue
            repo_dir = location.local_path
            has, _, _ = self.has_converter(repo_dir)
            if not has:
                continue
            results.append((repo_dir, self.docker_image_name(repo_dir)))
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
        collection = self._catalog_comp.collection
        selection = collection.select()
        if not selection.documents:
            click.echo("  no documents found in catalog")
            return
        extra = ["--no-cache"] if no_cache else []
        built_any = False
        for _name, _url, repo_dir in collection.iter_documents(
            selection.documents, selection.directories
        ):
            has, dockerfile, ctx = self.has_converter(repo_dir)
            if not has:
                continue
            image_name = self.docker_image_name(repo_dir)
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

    # ---------------------------------------------------------------------------
    # Per-document converter build and test logic
    # ---------------------------------------------------------------------------

    @classmethod
    def docker_image_name(cls, repo_dir: Path) -> str:
        name = repo_dir.resolve().name
        if name.startswith(cls.DOC_PREFIX):
            name = name[len(cls.DOC_PREFIX) :]
        return f"jejune:convert_{name}" if name else "jejune:convert"

    @staticmethod
    def has_converter(repo_dir: Path) -> tuple[bool, Path, Path]:
        """Return (has_converter, dockerfile, context)."""
        ctx = repo_dir / "DockerContext"
        df = ctx / "Dockerfile"
        return (ctx.is_dir() and df.exists()), df, ctx

    @classmethod
    def run_converter_test(
        cls, repo_dir: Path, no_cache: bool, no_build: bool
    ) -> tuple[str, str, str]:
        """Return (outcome, detail, verbose_output). outcome taken among skipped, build_failed, unchanged or changed."""
        has, dockerfile, context = cls.has_converter(repo_dir)
        if not has:
            return "skipped", "no DockerContext", ""
        image = cls.docker_image_name(repo_dir)
        verbose_lines: list[str] = []
        if not no_build:
            extra = ["--no-cache"] if no_cache else []
            build_result = subprocess.run(
                [
                    "docker",
                    "build",
                    *extra,
                    "-t",
                    image,
                    "-f",
                    str(dockerfile),
                    str(context),
                ],
                capture_output=True,
                text=True,
            )
            verbose_lines.extend(
                (build_result.stdout + build_result.stderr).strip().splitlines()
            )
            if build_result.returncode != 0:
                tail = (build_result.stderr or build_result.stdout).strip().splitlines()
                return (
                    "build_failed",
                    tail[-1] if tail else "build failed",
                    "\n".join(verbose_lines),
                )
        else:
            images_result = subprocess.run(
                ["docker", "images", "-q", image], capture_output=True, text=True
            )
            if not (images_result.returncode == 0 and images_result.stdout.strip()):
                return "build_failed", f"image {image!r} not found", ""
        run_result = subprocess.run(
            ["docker", "run", "--rm", image, "--test"], capture_output=True, text=True
        )
        verbose_lines.extend((run_result.stdout + run_result.stderr).strip().splitlines())
        return (
            ("unchanged", "tests passed", "\n".join(verbose_lines))
            if run_result.returncode == 0
            else ("changed", "tests failed", "\n".join(verbose_lines))
        )
