"""converters containerized component — tracks all per-repo converter images in a catalog."""

import json
import subprocess
from pathlib import Path

import click

from jejune_cli.components.catalog.component_catalog_file import CatalogFile
from jejune_cli.components.containers.component_cont_convert import CompConvert
from jejune_cli.core.component_containerized import ContComp
from jejune_cli.components.component_ecosystem import EcosystemDirectories
from jejune_cli.core.containerized_context import ContainerizedContext
from jejune_cli.components.containers.converter_commits import ConverterCommits
from jejune_cli.components.containers.converter_image_name import ConverterImageName
from jejune_cli.components.containers.converter_sources import (
    ConverterSource,
    ConverterSources,
)


class CompConverters(ContComp):
    DOC_PREFIX = ConverterImageName.DOC_PREFIX
    PDF_TO_MARKDOWN_NAME = ConverterSources.PDF_TO_MARKDOWN_NAME
    DEFAULT_DOCUMENT_SOURCE = ConverterSources.DEFAULT_DOCUMENT_SOURCE
    DEFAULT_PDF_TO_MARKDOWN_SOURCE = ConverterSources.DEFAULT_PDF_TO_MARKDOWN_SOURCE

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
        # pdf-to-markdown is a repository of the ecosystem (listed by `ecosystem
        # status`, updated by `ecosystem update`) as soon as it is cloned
        ecosystem.register_repository(
            self.name,
            self.PDF_TO_MARKDOWN_NAME,
            used_commits=self.image_pdf_to_markdown_commits,
        )
        ecosystem.register_document_images(self.name, self.image_document_commits)

    def image_variants(self, repo_dir_name: str) -> list[str]:
        """Every image name of the converter of *repo_dir_name* (whatever its local
        sources)."""
        return ConverterImageName.variants(
            ConverterImageName.CATALOG_OWNER, repo_dir_name
        )

    def image_pdf_to_markdown_commits(self) -> list[str]:
        """The pdf-to-markdown commits recorded in the built images of the documents
        of the catalog."""
        return [
            commit
            for repo_dir, _ in self._iter_local_converter_repos()
            for commit in ConverterCommits.labelled_commits(
                self._context.docker,
                self.image_variants(repo_dir.resolve().name),
                ConverterCommits.PDF_TO_MARKDOWN_COMMIT_LABEL,
            )
        ]

    def image_document_commits(self, document_name: str) -> list[str]:
        """The commits of the document *document_name* recorded in its built images."""
        return ConverterCommits.labelled_commits(
            self._context.docker,
            self.image_variants(document_name),
            ConverterCommits.DOCUMENT_COMMIT_LABEL,
        )

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
        # An image built from local sources (--local*) is as built as the default one
        return all(
            any(
                self._context.docker.image_exists(variant)
                for variant in ConverterImageName.variants(
                    ConverterImageName.CATALOG_OWNER, repo_dir.resolve().name
                )
            )
            for repo_dir, _ in repos
        )

    def locate_pdf_to_markdown(
        self, directories: EcosystemDirectories
    ) -> ConverterSource:
        return ConverterSources.locate_pdf_to_markdown(self._ecosystem, directories)

    @classmethod
    def image_source_summary(cls, image: str) -> str:
        """The sources *image* was built with, read from its labels (the default
        ones for an image without labels)."""
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Labels}}", image],
            capture_output=True,
            text=True,
        )
        labels = (
            (json.loads(inspected.stdout) or {}) if inspected.returncode == 0 else {}
        )
        document = labels.get(
            ConverterCommits.DOCUMENT_SOURCE_LABEL, cls.DEFAULT_DOCUMENT_SOURCE
        )
        pdf_to_markdown = labels.get(
            ConverterCommits.PDF_TO_MARKDOWN_SOURCE_LABEL,
            cls.DEFAULT_PDF_TO_MARKDOWN_SOURCE,
        )
        return f"document: {document}, pdf-to-markdown: {pdf_to_markdown}"

    def build(
        self,
        no_cache: bool = False,
        catalog_file: str | None = None,
        repo: str | None = None,
        root_dir: str | None = None,
        local_documents: bool = False,
        local_pdf_to_markdown: bool = False,
    ) -> None:
        collection = self._catalog_comp.collection
        selection = collection.select(catalog_file, repo, root_dir)
        if not selection.documents:
            click.echo("  no documents found in catalog")
            return
        built_any = False
        failed_images: list[str] = []
        token_files = CatalogFile(CatalogFile.resolve_path()).token_files()
        pdf_to_markdown = (
            self.locate_pdf_to_markdown(selection.directories)
            if local_pdf_to_markdown
            else ConverterSource()
        )
        for name, _url, repo_dir in collection.iter_documents(
            selection.documents, selection.directories
        ):
            has, dockerfile, ctx = self.has_converter(repo_dir)
            if not has:
                continue
            image_name = self.docker_image_name(
                repo_dir, local_documents, local_pdf_to_markdown
            )
            document = (
                ConverterSource(
                    self._ecosystem.locate(name, selection.directories).tier, repo_dir
                )
                if local_documents
                else ConverterSource()
            )
            click.echo(
                f"  Building {image_name} "
                f"(document: {document.label_value(self.DEFAULT_DOCUMENT_SOURCE)}, "
                f"pdf-to-markdown: "
                f"{pdf_to_markdown.label_value(self.DEFAULT_PDF_TO_MARKDOWN_SOURCE)}) ..."
            )
            try:
                ConverterSources.build_image(
                    self._context.git_access,
                    image_name=image_name,
                    dockerfile=dockerfile,
                    context_dir=ctx,
                    document=document,
                    document_urls=CompConvert.dockerfile_git_urls(dockerfile),
                    pdf_to_markdown=pdf_to_markdown,
                    token_file=token_files.get(name),
                    no_cache=no_cache,
                )
            except subprocess.CalledProcessError as error:
                click.echo(
                    click.style(
                        f"  docker build of {image_name} failed (exit code {error.returncode}), see the docker output above",
                        fg="red",
                    ),
                    err=True,
                )
                failed_images.append(image_name)
                continue
            built_any = True
        if failed_images:
            raise click.ClickException(
                f"{len(failed_images)} docker build(s) failed: "
                + ", ".join(failed_images)
            )
        if not built_any:
            click.echo("  no converter repos found in catalog")

    def check(self) -> tuple[str, str]:
        return "ok", ""

    # ---------------------------------------------------------------------------
    # Per-document converter build and test logic
    # ---------------------------------------------------------------------------

    @classmethod
    def docker_image_name(
        cls,
        repo_dir: Path,
        local_documents: bool = False,
        local_pdf_to_markdown: bool = False,
    ) -> str:
        return ConverterImageName.build(
            ConverterImageName.CATALOG_OWNER,
            repo_dir.resolve().name,
            local_documents,
            local_pdf_to_markdown,
        )

    @staticmethod
    def has_converter(repo_dir: Path) -> tuple[bool, Path, Path]:
        """Return (has_converter, dockerfile, context)."""
        ctx = repo_dir / "DockerContext"
        df = ctx / "Dockerfile"
        return (ctx.is_dir() and df.exists()), df, ctx

    def run_converter_test(
        self,
        repo_dir: Path,
        document_name: str,
        catalog_file: str | None,
        root_dir: str | None,
        no_cache: bool,
        local_documents: bool = False,
        local_pdf_to_markdown: bool = False,
    ) -> tuple[str, str, str]:
        """Return (outcome, detail, verbose_output). outcome taken among skipped,
        build_failed, image_not_found, unchanged or changed. The image built with
        the selected sources is built first when absent (or when no_cache)."""
        has, _, _ = self.has_converter(repo_dir)
        if not has:
            return "skipped", "no DockerContext", ""
        image = self.docker_image_name(repo_dir, local_documents, local_pdf_to_markdown)
        verbose_lines: list[str] = []
        if no_cache or not self._context.docker.image_exists(image):
            try:
                self.build(
                    no_cache,
                    catalog_file,
                    document_name,
                    root_dir,
                    local_documents,
                    local_pdf_to_markdown,
                )
            except click.ClickException as error:
                return "build_failed", error.format_message(), ""
            if not self._context.docker.image_exists(image):
                return "image_not_found", f"image {image!r} not found", ""
        run_result = subprocess.run(
            ["docker", "run", "--rm", image, "--test"], capture_output=True, text=True
        )
        verbose_lines.extend(
            (run_result.stdout + run_result.stderr).strip().splitlines()
        )
        sources = self.image_source_summary(image)
        return (
            ("unchanged", f"tests passed ({sources})", "\n".join(verbose_lines))
            if run_result.returncode == 0
            else ("changed", f"tests failed ({sources})", "\n".join(verbose_lines))
        )
