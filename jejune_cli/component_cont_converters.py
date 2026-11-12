"""converters containerized component — tracks all per-repo converter images in a catalog."""

import json
import subprocess
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import click

from .component_catalog_file import CatalogFile
from .component_cont_convert import CompConvert
from .component_containerized import ContComp
from .component_ecosystem import EcosystemDirectories, RepoTier
from .containerized_context import ContainerizedContext


@dataclass(frozen=True)
class ConverterSource:
    """Where an input of a converter image comes from: a local directory found in a
    tier of the ecosystem or, without any, the default one (the `git clone` of the
    Dockerfile for a document, the uv.lock version for pdf-to-markdown)."""

    tier: RepoTier | None = None
    path: Path | None = None

    @property
    def is_local(self) -> bool:
        return self.path is not None

    def label_value(self, default: str) -> str:
        return f"{self.tier}:{self.path}" if self.is_local else default


class CompConverters(ContComp):
    DOC_PREFIX = "jejune_doc_"
    PDF_TO_MARKDOWN_NAME = "pdf-to-markdown"
    # Names shared with the Dockerfile of every document (ARG, named build contexts)
    DOCUMENT_CONTEXT_NAME = "jejune-doc"
    DOCUMENT_SOURCE_ARGUMENT = "DOC_SOURCE"
    PDF_TO_MARKDOWN_SOURCE_ARGUMENT = "PDF_TO_MARKDOWN_SOURCE"
    # Image labels recording where the inputs of an image came from
    DOCUMENT_LABEL = "jejune.document"
    PDF_TO_MARKDOWN_LABEL = "jejune.pdf-to-markdown"
    DEFAULT_DOCUMENT_SOURCE = "git"
    DEFAULT_PDF_TO_MARKDOWN_SOURCE = "locked"

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

    def locate_pdf_to_markdown(self, directories: EcosystemDirectories) -> ConverterSource:
        """The local pdf-to-markdown: JEJUNE_ROOT_DIR first, then .jejune/tmp, else
        cloned into .jejune/tmp."""
        location = self._ecosystem.locate(self.PDF_TO_MARKDOWN_NAME, directories)
        if location.is_local:
            return ConverterSource(location.tier, location.local_path)
        return ConverterSource(
            "tmp", self._ecosystem.ensure_local(self.PDF_TO_MARKDOWN_NAME)
        )

    @classmethod
    def source_arguments(
        cls, document: ConverterSource, pdf_to_markdown: ConverterSource
    ) -> list[str]:
        """The `docker build` arguments selecting the local sources (the default
        ones when absent) and labelling the image with the sources it was built with."""
        arguments: list[str] = []
        for source, context_name, argument_name in (
            (document, cls.DOCUMENT_CONTEXT_NAME, cls.DOCUMENT_SOURCE_ARGUMENT),
            (
                pdf_to_markdown,
                cls.PDF_TO_MARKDOWN_NAME,
                cls.PDF_TO_MARKDOWN_SOURCE_ARGUMENT,
            ),
        ):
            if source.is_local:
                arguments += [
                    "--build-arg",
                    f"{argument_name}=local",
                    "--build-context",
                    f"{context_name}={source.path}",
                ]
        arguments += [
            "--label",
            f"{cls.DOCUMENT_LABEL}={document.label_value(cls.DEFAULT_DOCUMENT_SOURCE)}",
            "--label",
            f"{cls.PDF_TO_MARKDOWN_LABEL}="
            f"{pdf_to_markdown.label_value(cls.DEFAULT_PDF_TO_MARKDOWN_SOURCE)}",
        ]
        return arguments

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
        document = labels.get(cls.DOCUMENT_LABEL, cls.DEFAULT_DOCUMENT_SOURCE)
        pdf_to_markdown = labels.get(
            cls.PDF_TO_MARKDOWN_LABEL, cls.DEFAULT_PDF_TO_MARKDOWN_SOURCE
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
        extra = ["--no-cache"] if no_cache else []
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
            image_name = self.docker_image_name(repo_dir)
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
            # Private repositories are cloned with the credentials handed over as
            # a BuildKit secret: they never end up in an image layer. A local
            # document is not cloned: no credentials needed.
            with (
                nullcontext(None)
                if document.is_local
                else self._context.git_access.credentials_file(
                    CompConvert.dockerfile_git_urls(dockerfile), token_files.get(name)
                )
            ) as credentials:
                secret = (
                    ["--secret", f"id=git_credentials,src={credentials}"]
                    if credentials
                    else []
                )
                try:
                    subprocess.run(
                        [
                            "docker",
                            "build",
                            *extra,
                            *secret,
                            *self.source_arguments(document, pdf_to_markdown),
                            "-t",
                            image_name,
                            "-f",
                            str(dockerfile),
                            str(ctx),
                        ],
                        check=True,
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
        verbose_lines.extend(
            (run_result.stdout + run_result.stderr).strip().splitlines()
        )
        sources = cls.image_source_summary(image)
        return (
            ("unchanged", f"tests passed ({sources})", "\n".join(verbose_lines))
            if run_result.returncode == 0
            else ("changed", f"tests failed ({sources})", "\n".join(verbose_lines))
        )
