"""Docker image names of the document converters.

Two roles build a converter image of the same document: the catalog-contributor
(all the documents of a catalog) and the doc-steward (the document of the current
directory). The owner and the local sources of the image are part of its tag, so
that none of these builds silently overwrites another one.
"""

import re
from dataclasses import dataclass

import click


class ConverterImageNameError(click.ClickException):
    """The generated image name is not accepted by docker."""


@dataclass(frozen=True)
class ParsedConverterImage:
    """The parts of the name of a converter image: see ConverterImageName.parse."""

    owner: str
    slug: str
    suffix: str


class ConverterImageName:
    REPOSITORY = "jejune"
    DOC_PREFIX = "jejune_doc_"
    CATALOG_OWNER = "catalog"
    DOCUMENT_OWNER = "doc"
    LOCAL_DOCUMENT_SUFFIX = "-local_doc"
    LOCAL_PDF_TO_MARKDOWN_SUFFIX = "-local_pdf"
    LOCAL_SUFFIX = "-local"
    # Docker limits: 128 characters for a tag, 255 for a whole image reference
    MAX_TAG_LENGTH = 128
    MAX_REFERENCE_LENGTH = 255
    TAG_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

    @classmethod
    def slug(cls, repo_dir_name: str) -> str:
        return repo_dir_name.removeprefix(cls.DOC_PREFIX)

    @classmethod
    def local_suffix(cls, local_documents: bool, local_pdf_to_markdown: bool) -> str:
        if local_documents and local_pdf_to_markdown:
            return cls.LOCAL_SUFFIX
        if local_documents:
            return cls.LOCAL_DOCUMENT_SUFFIX
        if local_pdf_to_markdown:
            return cls.LOCAL_PDF_TO_MARKDOWN_SUFFIX
        return ""

    @classmethod
    def build(
        cls,
        owner: str,
        repo_dir_name: str,
        local_documents: bool = False,
        local_pdf_to_markdown: bool = False,
    ) -> str:
        """The image reference of the converter of *repo_dir_name* built for *owner*.
        Raises ConverterImageNameError when docker would refuse it."""
        slug = cls.slug(repo_dir_name)
        tag = (
            f"convert_{owner}{'_' + slug if slug else ''}"
            f"{cls.local_suffix(local_documents, local_pdf_to_markdown)}"
        )
        reference = f"{cls.REPOSITORY}:{tag}"
        if len(tag) > cls.MAX_TAG_LENGTH:
            raise ConverterImageNameError(
                f"image tag {tag!r} of the document {repo_dir_name!r} has {len(tag)} "
                f"characters: docker accepts at most {cls.MAX_TAG_LENGTH}"
            )
        if len(reference) > cls.MAX_REFERENCE_LENGTH:
            raise ConverterImageNameError(
                f"image name {reference!r} of the document {repo_dir_name!r} has "
                f"{len(reference)} characters: docker accepts at most "
                f"{cls.MAX_REFERENCE_LENGTH}"
            )
        if not cls.TAG_PATTERN.fullmatch(tag):
            raise ConverterImageNameError(
                f"image tag {tag!r} of the document {repo_dir_name!r} is not accepted "
                f"by docker: only letters, digits, '_', '.' and '-' are allowed"
            )
        return reference

    @classmethod
    def parse(cls, image: str) -> ParsedConverterImage | None:
        """The inverse of build: the owner, the slug and the local suffix of the
        converter image *image* (None when it is not a converter image)."""
        repository, _, tag = image.partition(":")
        if repository != cls.REPOSITORY:
            return None
        for owner in (cls.CATALOG_OWNER, cls.DOCUMENT_OWNER):
            prefix = f"convert_{owner}_"
            if tag.startswith(prefix):
                remainder = tag.removeprefix(prefix)
                break
        else:
            return None
        # The longest suffix first: LOCAL_SUFFIX is a prefix of the other ones
        for suffix in (
            cls.LOCAL_DOCUMENT_SUFFIX,
            cls.LOCAL_PDF_TO_MARKDOWN_SUFFIX,
            cls.LOCAL_SUFFIX,
        ):
            if remainder.endswith(suffix):
                remainder = remainder.removesuffix(suffix)
                break
        else:
            suffix = ""
        return ParsedConverterImage(owner, remainder, suffix) if remainder else None

    @classmethod
    def repository_names(cls, slug: str) -> list[str]:
        """The names the document repository of a converter image of *slug* can have:
        the one with the DOC_PREFIX, else the slug itself."""
        return [cls.DOC_PREFIX + slug, slug]

    @classmethod
    def variants(cls, owner: str, repo_dir_name: str) -> list[str]:
        """Every image name of the converter of *repo_dir_name* for *owner*, whatever
        its local sources."""
        return [
            cls.build(owner, repo_dir_name, local_documents, local_pdf_to_markdown)
            for local_documents in (False, True)
            for local_pdf_to_markdown in (False, True)
        ]
