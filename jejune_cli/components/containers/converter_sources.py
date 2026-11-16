"""Sources of the inputs of a converter image (document, pdf-to-markdown).

Shared by the two roles building a converter image: the catalog-contributor
(`converters build`) and the doc-steward (`convert build`).
"""

from dataclasses import dataclass
from pathlib import Path

from jejune_cli.components.component_ecosystem import EcosystemDirectories
from jejune_cli.components.containers.converter_commits import ConverterCommits
from jejune_cli.core._package_paths import PdfToMarkdownConfig


@dataclass(frozen=True)
class ConverterSource:
    """Where an input of a converter image comes from: a local directory found in a
    tier of the ecosystem (or the current directory) or, without any, the default
    one (the `git clone` of the Dockerfile for a document, the uv.lock version for
    pdf-to-markdown)."""

    tier: str | None = None
    path: Path | None = None

    @property
    def is_local(self) -> bool:
        return self.path is not None

    def label_value(self, default: str) -> str:
        return f"{self.tier}:{self.path}" if self.is_local else default


class ConverterSources:
    PDF_TO_MARKDOWN_NAME = PdfToMarkdownConfig.REPO_NAME
    # Names shared with the Dockerfile of every document (ARG, named build contexts)
    DOCUMENT_CONTEXT_NAME = "jejune-doc"
    DOCUMENT_SOURCE_ARGUMENT = "DOC_SOURCE"
    PDF_TO_MARKDOWN_SOURCE_ARGUMENT = "PDF_TO_MARKDOWN_SOURCE"
    DEFAULT_DOCUMENT_SOURCE = "git"
    DEFAULT_PDF_TO_MARKDOWN_SOURCE = "locked"

    @classmethod
    def locate_pdf_to_markdown(
        cls, ecosystem, directories: EcosystemDirectories
    ) -> ConverterSource:
        """The local pdf-to-markdown: JEJUNE_ROOT_DIR first, then .jejune/tmp, else
        cloned into .jejune/tmp.  A clone of .jejune/tmp is given its whole git
        history (the commit count is part of the pdf-to-markdown version); a
        checkout of JEJUNE_ROOT_DIR belongs to the user and is left untouched."""
        location = ecosystem.locate(cls.PDF_TO_MARKDOWN_NAME, directories)
        if location.is_local:
            source = ConverterSource(location.tier, location.local_path)
        else:
            source = ConverterSource(
                "tmp", ecosystem.ensure_local(cls.PDF_TO_MARKDOWN_NAME)
            )
        if source.tier == "tmp":
            ecosystem.unshallow(source.path)
        return source

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
            f"{ConverterCommits.DOCUMENT_SOURCE_LABEL}={document.label_value(cls.DEFAULT_DOCUMENT_SOURCE)}",
            "--label",
            f"{ConverterCommits.PDF_TO_MARKDOWN_SOURCE_LABEL}="
            f"{pdf_to_markdown.label_value(cls.DEFAULT_PDF_TO_MARKDOWN_SOURCE)}",
        ]
        return arguments
