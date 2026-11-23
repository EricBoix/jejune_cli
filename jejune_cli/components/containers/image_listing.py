"""The rows of `jejune images list`.

The images of the components of a role, with the commits recorded in them compared
to the ones of the sources the ecosystem designates now: a converter image records
the commit of its document and the one of pdf-to-markdown, another image built by
jejune records the commit of its repository (or, when it is pulled, shows its
version).
"""

from dataclasses import dataclass
from pathlib import Path

from jejune_cli.components.component_ecosystem import EcosystemDirectories
from jejune_cli.components.containers.converter_commits import (
    ConverterCommits,
    ImageAlignment,
)
from jejune_cli.components.containers.converter_image_name import (
    ConverterImageName,
    ParsedConverterImage,
)
from jejune_cli.core._package_paths import PdfToMarkdownConfig


@dataclass(frozen=True)
class CommitCell:
    """A commit recorded in an image (shortened, blank when the image has none) and
    whether it is the one designated by the ecosystem."""

    commit: str
    alignment: ImageAlignment


@dataclass(frozen=True)
class ConvertImageRow:
    """A converter image: *summary* is the verdict about its two inputs."""

    name: str
    summary: ImageAlignment
    document: CommitCell
    pdf_to_markdown: CommitCell


@dataclass(frozen=True)
class OtherImageRow:
    """Another image of a component: *repository* is the (shortened) commit of the
    repository recorded in the image or, when it records none, its version (blank
    when it has neither). *summary* is None when there is nothing to compare."""

    name: str
    summary: ImageAlignment | None
    repository: str


class ImageListing:
    REPOSITORY_COMMIT_LABEL = "jejune.repository-commit"
    VERSION_LABEL = "org.opencontainers.image.version"
    IMAGE_PREFIX = f"{ConverterImageName.REPOSITORY}:"

    def __init__(
        self,
        ecosystem,
        docker,
        directories: EcosystemDirectories,
        cloned_documents: dict[str, Path],
        catalog_documents: set[str],
    ) -> None:
        """*cloned_documents* maps the name of the document repositories cloned
        locally to their path; *catalog_documents* are the names of the ones the
        catalog lists. A document in neither of them is not in the ecosystem."""
        self._ecosystem = ecosystem
        self._docker = docker
        self._directories = directories
        self._cloned_documents = cloned_documents
        self._catalog_documents = catalog_documents
        # slug of a document -> (is it in the ecosystem, the commit designated)
        self._document_designations: dict[str, tuple[bool, str | None]] = {}
        # The pdf-to-markdown the ecosystem designates is the same for every document
        self._pdf_to_markdown_designation: tuple[str | None] | None = None

    def convert_rows(self, components: list) -> list[ConvertImageRow]:
        """The converter images, existing locally, of the *components* that build
        some, sorted by name."""
        installed_images = self._docker.list_images()
        rows: list[ConvertImageRow] = []
        for component in components:
            owner = component.converter_image_owner()
            if owner is None:
                continue
            for image in installed_images:
                parsed = ConverterImageName.parse(image)
                if (
                    parsed is not None
                    and parsed.owner == owner
                    and component.handles_document(parsed.slug)
                ):
                    rows.append(self._convert_row(image, parsed))
        return sorted(rows, key=lambda row: row.name)

    def other_rows(self, components: list) -> list[OtherImageRow]:
        """The images of the *components* that are neither converter images nor
        external ones, existing locally, sorted by name."""
        rows: list[OtherImageRow] = []
        for component in components:
            if (
                component.converter_image_owner() is not None
                or component.is_external_image
                or not component.image_name.startswith(self.IMAGE_PREFIX)
            ):
                continue
            image = component.built_image_name()
            if image is not None:
                rows.append(self._other_row(component, image))
        return sorted(rows, key=lambda row: row.name)

    def _convert_row(self, image: str, parsed: ParsedConverterImage) -> ConvertImageRow:
        labels = ConverterCommits.image_labels(image)
        document = self._document_cell(
            parsed.slug, labels.get(ConverterCommits.DOCUMENT_COMMIT_LABEL)
        )
        pdf_to_markdown = self._pdf_to_markdown_cell(
            labels.get(ConverterCommits.PDF_TO_MARKDOWN_COMMIT_LABEL)
        )
        summary = ConverterCommits.combine(
            [document.alignment, pdf_to_markdown.alignment]
        )
        return ConvertImageRow(image, summary, document, pdf_to_markdown)

    def _document_cell(self, slug: str, recorded_commit: str | None) -> CommitCell:
        if recorded_commit is None:
            return CommitCell("", ImageAlignment.UNKNOWN)
        in_ecosystem, designated_commit = self._document_designation(slug)
        alignment = (
            ConverterCommits.compare(recorded_commit, designated_commit)
            if in_ecosystem
            else ImageAlignment.ORPHAN
        )
        return CommitCell(ConverterCommits.short_commit(recorded_commit), alignment)

    def _pdf_to_markdown_cell(self, recorded_commit: str | None) -> CommitCell:
        if recorded_commit is None:
            return CommitCell("", ImageAlignment.UNKNOWN)
        if self._pdf_to_markdown_designation is None:
            self._pdf_to_markdown_designation = (
                self._ecosystem.designated_commit(
                    PdfToMarkdownConfig.REPO_NAME, self._directories
                ),
            )
        (designated_commit,) = self._pdf_to_markdown_designation
        return CommitCell(
            ConverterCommits.short_commit(recorded_commit),
            ConverterCommits.compare(recorded_commit, designated_commit),
        )

    def _document_designation(self, slug: str) -> tuple[bool, str | None]:
        """Is the document of the converter images of *slug* in the ecosystem and, if
        so, which commit does the ecosystem designate for it (None when it cannot be
        told)? A local clone designates its own commit, else the remote HEAD does."""
        if slug not in self._document_designations:
            self._document_designations[slug] = self._find_document_designation(slug)
        return self._document_designations[slug]

    def _find_document_designation(self, slug: str) -> tuple[bool, str | None]:
        repository_names = ConverterImageName.repository_names(slug)
        for name in repository_names:
            if name in self._cloned_documents:
                return True, self._ecosystem.checkout_commit(
                    self._cloned_documents[name]
                )
        for name in repository_names:
            if name in self._catalog_documents:
                return True, self._ecosystem.designated_commit(name, self._directories)
        return False, None

    def _other_row(self, component, image: str) -> OtherImageRow:
        labels = ConverterCommits.image_labels(image)
        recorded_commit = labels.get(self.REPOSITORY_COMMIT_LABEL)
        if recorded_commit is None:
            return OtherImageRow(image, None, labels.get(self.VERSION_LABEL, ""))
        repository_name = self._ecosystem.component_repository_name(component)
        designated_commit = (
            self._ecosystem.designated_commit(repository_name, self._directories)
            if repository_name
            else None
        )
        return OtherImageRow(
            image,
            ConverterCommits.compare(recorded_commit, designated_commit),
            ConverterCommits.short_commit(recorded_commit),
        )
