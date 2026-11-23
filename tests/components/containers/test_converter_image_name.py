from pathlib import Path

import pytest

from jejune_cli.components.containers.component_cont_converters import CompConverters
from jejune_cli.components.containers.converter_image_name import (
    ConverterImageName,
    ConverterImageNameError,
    ParsedConverterImage,
)


@pytest.mark.parametrize(
    "local_documents, local_pdf_to_markdown, expected",
    [
        (False, False, "jejune:convert_catalog_book"),
        (True, False, "jejune:convert_catalog_book-local_doc"),
        (False, True, "jejune:convert_catalog_book-local_pdf"),
        (True, True, "jejune:convert_catalog_book-local"),
    ],
)
def test_catalog_image_name_follows_the_local_sources(
    local_documents, local_pdf_to_markdown, expected
):
    assert (
        CompConverters.docker_image_name(
            Path("/somewhere/jejune_doc_book"), local_documents, local_pdf_to_markdown
        )
        == expected
    )


def test_catalog_and_doc_owners_never_share_an_image_name():
    assert ConverterImageName.build(
        ConverterImageName.CATALOG_OWNER, "jejune_doc_book"
    ) != ConverterImageName.build(ConverterImageName.DOCUMENT_OWNER, "jejune_doc_book")


def test_variants_list_the_four_local_source_combinations():
    assert len(set(ConverterImageName.variants("catalog", "jejune_doc_book"))) == 4


def test_too_long_tag_is_refused():
    with pytest.raises(ConverterImageNameError, match="at most 128"):
        ConverterImageName.build(ConverterImageName.CATALOG_OWNER, "x" * 200)


def test_tag_with_forbidden_characters_is_refused():
    with pytest.raises(ConverterImageNameError, match="not accepted"):
        ConverterImageName.build(ConverterImageName.DOCUMENT_OWNER, "my book")


@pytest.mark.parametrize("owner", ["catalog", "doc"])
@pytest.mark.parametrize(
    "local_documents, local_pdf_to_markdown, suffix",
    [
        (False, False, ""),
        (True, False, "-local_doc"),
        (False, True, "-local_pdf"),
        (True, True, "-local"),
    ],
)
def test_parse_is_the_inverse_of_build(
    owner, local_documents, local_pdf_to_markdown, suffix
):
    image = ConverterImageName.build(
        owner, "jejune_doc_book", local_documents, local_pdf_to_markdown
    )
    assert ConverterImageName.parse(image) == ParsedConverterImage(
        owner, "book", suffix
    )


@pytest.mark.parametrize(
    "image",
    [
        "jejune:hub",
        "jejune:convert_book",
        "jejune:convert_catalog_",
        "jejune:convert_catalog_-local",
        "other:convert_catalog_book",
        "convert_catalog_book",
        "",
    ],
)
def test_parse_ignores_what_is_not_a_converter_image(image):
    assert ConverterImageName.parse(image) is None


def test_repository_names_of_a_slug_are_the_prefixed_one_and_the_slug():
    assert ConverterImageName.repository_names("book") == ["jejune_doc_book", "book"]
