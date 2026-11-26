from pathlib import Path
from types import SimpleNamespace

import pytest

from jejune_cli.components.component_ecosystem import EcosystemDirectories
from jejune_cli.components.containers.converter_commits import (
    ConverterCommits,
    ImageAlignment,
)
from jejune_cli.components.containers.image_listing import (
    CommitCell,
    ConvertImageRow,
    ImageListing,
    OtherImageRow,
)

DOCUMENT_COMMIT = "8e8834cd878ecb47fe306edeffb3fe78bb91b79e"
PDF_TO_MARKDOWN_COMMIT = "8ce4cee8428b9984ee2c13c565c8a0e2d1da1ce2"
STALE_COMMIT = "7fe327e3d9c3add067b44108980a86f904bbf92c"
DIRTY = ConverterCommits.DIRTY_SUFFIX
DOCUMENT_COMMIT_LABEL = ConverterCommits.DOCUMENT_COMMIT_LABEL
PDF_TO_MARKDOWN_COMMIT_LABEL = ConverterCommits.PDF_TO_MARKDOWN_COMMIT_LABEL
DOCUMENT_PATH = Path("/root/jejune_doc_Collecting_Gold_Dust")
CATALOG_IMAGE = "jejune:convert_catalog_Collecting_Gold_Dust"


class FakeEcosystem:
    """Designates a commit per repository name; the document clones have their own."""

    def __init__(self, designated=None, checkouts=None, repository_names=None):
        self.designated = designated or {"pdf-to-markdown": PDF_TO_MARKDOWN_COMMIT}
        self.checkouts = checkouts or {DOCUMENT_PATH: DOCUMENT_COMMIT}
        self.repository_names = repository_names or {}

    def designated_commit(self, name, directories):
        return self.designated.get(name)

    def checkout_commit(self, checkout):
        return self.checkouts.get(checkout)

    def component_repository_name(self, component):
        return self.repository_names.get(component.name)


class FakeDocker:
    def __init__(self, images):
        self.images = images

    def list_images(self):
        return self.images


class FakeLabels:
    """Plays `ConverterCommits.image_labels`."""

    def __init__(self, monkeypatch, labels):
        self.labels = labels
        monkeypatch.setattr(
            ConverterCommits, "image_labels", lambda image: self.labels.get(image, {})
        )


def converter_component(owner="catalog", handles=lambda slug: True):
    return SimpleNamespace(
        name="converters",
        converter_image_owner=lambda: owner,
        handles_document=handles,
    )


def other_component(
    name="hub",
    image_name="jejune:hub",
    built_image_name="jejune:hub",
    is_external_image=False,
):
    return SimpleNamespace(
        name=name,
        converter_image_owner=lambda: None,
        is_external_image=is_external_image,
        image_name=image_name,
        built_image_name=lambda: built_image_name,
    )


def listing(
    images=(),
    ecosystem=None,
    cloned_documents=None,
    catalog_documents=(),
):
    return ImageListing(
        ecosystem or FakeEcosystem(),
        FakeDocker(list(images)),
        EcosystemDirectories(None, None),
        (
            {"jejune_doc_Collecting_Gold_Dust": DOCUMENT_PATH}
            if cloned_documents is None
            else cloned_documents
        ),
        set(catalog_documents),
    )


def convert_labels(document_commit, pdf_to_markdown_commit):
    return {
        DOCUMENT_COMMIT_LABEL: document_commit,
        PDF_TO_MARKDOWN_COMMIT_LABEL: pdf_to_markdown_commit,
    }


def test_the_three_variants_of_a_document_are_told_apart(monkeypatch):
    local_pdf_image = CATALOG_IMAGE + "-local_pdf"
    FakeLabels(
        monkeypatch,
        {
            CATALOG_IMAGE: convert_labels(DOCUMENT_COMMIT, STALE_COMMIT),
            CATALOG_IMAGE
            + "-local": convert_labels(DOCUMENT_COMMIT, PDF_TO_MARKDOWN_COMMIT),
            local_pdf_image: convert_labels(STALE_COMMIT, STALE_COMMIT + DIRTY),
        },
    )
    rows = listing(
        [CATALOG_IMAGE, CATALOG_IMAGE + "-local", local_pdf_image]
    ).convert_rows([converter_component()])
    assert rows == [
        ConvertImageRow(
            CATALOG_IMAGE,
            ImageAlignment.MISALIGNED,
            CommitCell("8e8834c", ImageAlignment.ALIGNED),
            CommitCell("7fe327e", ImageAlignment.MISALIGNED),
        ),
        ConvertImageRow(
            CATALOG_IMAGE + "-local",
            ImageAlignment.ALIGNED,
            CommitCell("8e8834c", ImageAlignment.ALIGNED),
            CommitCell("8ce4cee", ImageAlignment.ALIGNED),
        ),
        ConvertImageRow(
            local_pdf_image,
            ImageAlignment.MISALIGNED,
            CommitCell("7fe327e", ImageAlignment.MISALIGNED),
            CommitCell("7fe327e-dirty", ImageAlignment.MISALIGNED),
        ),
    ]


def test_the_same_dirty_commit_is_unknown(monkeypatch):
    FakeLabels(
        monkeypatch,
        {
            CATALOG_IMAGE: convert_labels(
                DOCUMENT_COMMIT, PDF_TO_MARKDOWN_COMMIT + DIRTY
            )
        },
    )
    ecosystem = FakeEcosystem(
        designated={"pdf-to-markdown": PDF_TO_MARKDOWN_COMMIT + DIRTY}
    )
    (row,) = listing([CATALOG_IMAGE], ecosystem).convert_rows([converter_component()])
    assert row.pdf_to_markdown.alignment is ImageAlignment.UNKNOWN
    assert row.summary is ImageAlignment.UNKNOWN


def test_an_input_the_image_does_not_record_is_unknown_and_blank(monkeypatch):
    FakeLabels(monkeypatch, {CATALOG_IMAGE: {DOCUMENT_COMMIT_LABEL: DOCUMENT_COMMIT}})
    (row,) = listing([CATALOG_IMAGE]).convert_rows([converter_component()])
    assert row.document == CommitCell("8e8834c", ImageAlignment.ALIGNED)
    assert row.pdf_to_markdown == CommitCell("", ImageAlignment.UNKNOWN)
    assert row.summary is ImageAlignment.UNKNOWN


def test_a_document_not_in_the_ecosystem_is_an_orphan(monkeypatch):
    FakeLabels(
        monkeypatch,
        {CATALOG_IMAGE: convert_labels(DOCUMENT_COMMIT, PDF_TO_MARKDOWN_COMMIT)},
    )
    (row,) = listing([CATALOG_IMAGE], cloned_documents={}).convert_rows(
        [converter_component()]
    )
    assert row.document == CommitCell("8e8834c", ImageAlignment.ORPHAN)
    assert row.pdf_to_markdown.alignment is ImageAlignment.ALIGNED
    assert row.summary is ImageAlignment.ORPHAN


def test_a_known_difference_prevails_over_an_orphan_document(monkeypatch):
    FakeLabels(
        monkeypatch,
        {CATALOG_IMAGE: convert_labels(DOCUMENT_COMMIT, STALE_COMMIT)},
    )
    (row,) = listing([CATALOG_IMAGE], cloned_documents={}).convert_rows(
        [converter_component()]
    )
    assert row.summary is ImageAlignment.MISALIGNED


def test_a_document_only_in_the_catalog_designates_its_remote_head(monkeypatch):
    FakeLabels(
        monkeypatch,
        {CATALOG_IMAGE: convert_labels(DOCUMENT_COMMIT, PDF_TO_MARKDOWN_COMMIT)},
    )
    ecosystem = FakeEcosystem(
        designated={
            "pdf-to-markdown": PDF_TO_MARKDOWN_COMMIT,
            "jejune_doc_Collecting_Gold_Dust": STALE_COMMIT,
        }
    )
    (row,) = listing(
        [CATALOG_IMAGE],
        ecosystem,
        cloned_documents={},
        catalog_documents=["jejune_doc_Collecting_Gold_Dust"],
    ).convert_rows([converter_component()])
    assert row.document.alignment is ImageAlignment.MISALIGNED


def test_an_unreachable_remote_makes_the_image_unknown(monkeypatch):
    FakeLabels(
        monkeypatch,
        {CATALOG_IMAGE: convert_labels(DOCUMENT_COMMIT, PDF_TO_MARKDOWN_COMMIT)},
    )
    ecosystem = FakeEcosystem(designated={})
    (row,) = listing(
        [CATALOG_IMAGE],
        ecosystem,
        cloned_documents={},
        catalog_documents=["jejune_doc_Collecting_Gold_Dust"],
    ).convert_rows([converter_component()])
    assert row.summary is ImageAlignment.UNKNOWN


def test_only_the_images_of_the_owner_and_of_the_handled_documents_are_listed(
    monkeypatch,
):
    FakeLabels(monkeypatch, {})
    images = [
        "jejune:convert_catalog_Mine",
        "jejune:convert_doc_Mine",
        "jejune:convert_doc_Other",
        "jejune:hub",
        "other:convert_doc_Mine",
        "jejune:convert_Mine",
    ]
    rows = listing(images).convert_rows(
        [converter_component("doc", handles=lambda slug: slug == "Mine")]
    )
    assert [row.name for row in rows] == ["jejune:convert_doc_Mine"]
    assert listing(images).convert_rows([other_component()]) == []


def test_other_images_compare_their_repository_commit_to_the_designated_one(
    monkeypatch,
):
    label = ImageListing.REPOSITORY_COMMIT_LABEL
    FakeLabels(
        monkeypatch,
        {
            "jejune:hub": {label: DOCUMENT_COMMIT},
            "jejune:docs": {label: STALE_COMMIT},
            "jejune:unknown": {label: STALE_COMMIT},
        },
    )
    ecosystem = FakeEcosystem(
        designated={"jejune_hub": DOCUMENT_COMMIT, "jejune_docs": DOCUMENT_COMMIT},
        repository_names={"hub": "jejune_hub", "docs": "jejune_docs"},
    )
    rows = listing([], ecosystem).other_rows(
        [
            other_component(),
            other_component("docs", "jejune:docs", "jejune:docs"),
            other_component("unknown", "jejune:unknown", "jejune:unknown"),
        ]
    )
    assert rows == [
        OtherImageRow(
            "jejune:docs", ImageAlignment.MISALIGNED, "7fe327e", repository_name="jejune_docs"
        ),
        OtherImageRow(
            "jejune:hub", ImageAlignment.ALIGNED, "8e8834c", repository_name="jejune_hub"
        ),
        OtherImageRow("jejune:unknown", ImageAlignment.UNKNOWN, "7fe327e"),
    ]


def test_a_pulled_image_shows_its_version_and_nothing_to_compare(monkeypatch):
    FakeLabels(
        monkeypatch,
        {
            "jejune:browser": {ImageListing.VERSION_LABEL: "4.145.2-ls377"},
            "jejune:bare": {},
        },
    )
    rows = listing().other_rows(
        [
            other_component("browser", "jejune:browser", "jejune:browser"),
            other_component("bare", "jejune:bare", "jejune:bare"),
        ]
    )
    assert rows == [
        OtherImageRow("jejune:bare", None, ""),
        OtherImageRow("jejune:browser", None, "4.145.2-ls377"),
    ]


def test_other_images_are_the_built_jejune_ones_of_no_converter(monkeypatch):
    FakeLabels(monkeypatch, {"jejune:compose-hub": {}})
    rows = listing().other_rows(
        [
            # Built by docker compose under its own name
            other_component(built_image_name="jejune:compose-hub"),
            other_component("external", "oxigraph/oxigraph", "oxigraph/oxigraph"),
            other_component("flagged", is_external_image=True),
            other_component("missing", "jejune:missing", None),
            converter_component(),
        ]
    )
    assert [row.name for row in rows] == ["jejune:compose-hub"]


def test_unbuilt_images_are_listed_on_demand_as_unavailable(monkeypatch):
    FakeLabels(monkeypatch, {})
    rows = listing().other_rows(
        [other_component("missing", "jejune:missing", None)], include_unbuilt=True
    )
    assert rows == [OtherImageRow("jejune:missing", None, "", available=False)]


@pytest.mark.parametrize("image_count", [1, 3])
def test_the_pdf_to_markdown_is_designated_once(monkeypatch, image_count):
    images = [f"{CATALOG_IMAGE}{suffix}" for suffix in ("", "-local", "-local_pdf")]
    FakeLabels(
        monkeypatch,
        {
            image: convert_labels(DOCUMENT_COMMIT, PDF_TO_MARKDOWN_COMMIT)
            for image in images
        },
    )
    calls = []
    ecosystem = FakeEcosystem()
    designated_commit = ecosystem.designated_commit
    ecosystem.designated_commit = lambda name, directories: (
        calls.append(name) or designated_commit(name, directories)
    )
    listing(images[:image_count], ecosystem).convert_rows([converter_component()])
    assert calls == ["pdf-to-markdown"]
