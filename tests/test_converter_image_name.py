from pathlib import Path

import pytest

from jejune_cli.component_cont_converters import CompConverters
from jejune_cli.converter_image_name import (
    ConverterImageName,
    ConverterImageNameError,
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
