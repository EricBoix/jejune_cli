from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from jejune_cli.click import click_group_images
from jejune_cli.components.component_ecosystem import EcosystemDirectories
from jejune_cli.components.containers.converter_commits import ConverterCommits
from jejune_cli.components.containers.image_listing import ImageListing

DOCUMENT_COMMIT = "8e8834cd878ecb47fe306edeffb3fe78bb91b79e"
PDF_TO_MARKDOWN_COMMIT = "8ce4cee8428b9984ee2c13c565c8a0e2d1da1ce2"
STALE_COMMIT = "7fe327e3d9c3add067b44108980a86f904bbf92c"
DOCUMENT_PATH = Path("/root/jejune_doc_Collecting_Gold_Dust")
CATALOG_IMAGE = "jejune:convert_catalog_Collecting_Gold_Dust"


class FakeContComp:
    """Stands for ContComp, which the command filters the components of the role by.
    Hashable, as the components of the role are kept in a set."""

    is_external_image = False

    def __init__(self, name, **attributes):
        self.name = name
        self.__dict__.update(attributes)

    def converter_image_owner(self):
        return None


class FakeEcosystem:
    def resolve_dirs(self):
        return EcosystemDirectories(None, None)

    def discover_doc_repos(self, directories, remote_names=None):
        return [
            (
                "jejune_doc_Collecting_Gold_Dust",
                "root",
                str(DOCUMENT_PATH),
                True,
            )
        ]

    def cwd_doc_repo(self):
        return self.discover_doc_repos(None)[0]

    def checkout_commit(self, checkout):
        return DOCUMENT_COMMIT

    def designated_commit(self, name, directories):
        return {"pdf-to-markdown": PDF_TO_MARKDOWN_COMMIT}.get(name)

    def component_repository_name(self, component):
        return "jejune_hub"


class FakeDocker:
    def __init__(self, images, status="ok"):
        self.images = images
        self.status = status

    def check(self):
        return self.status, "docker not found on PATH" if self.status != "ok" else ""

    def list_images(self):
        return self.images


class FakeComponentRegistry:
    def __init__(self, components):
        self._components = components

    def get(self, name):
        return self._components[name]


class FakeApplication:
    def __init__(self, components, images, docker_status="ok"):
        self.component_registry = FakeComponentRegistry(
            {
                "docker-command": FakeDocker(images, docker_status),
                "ecosystem": FakeEcosystem(),
            }
        )
        self.role_registry = SimpleNamespace(
            detect_role=lambda: SimpleNamespace(name="catalog-contributor"),
            role_components=lambda role: set(components),
            role_is_doc_steward_family=lambda role: False,
        )


@pytest.fixture
def invoke(monkeypatch):
    monkeypatch.setattr(click_group_images, "AppContext", FakeApplication)
    monkeypatch.setattr(click_group_images, "ContComp", FakeContComp)
    monkeypatch.setattr(
        click_group_images,
        "_catalog_document_names",
        lambda: {"jejune_doc_Collecting_Gold_Dust"},
    )

    def run(components, images, arguments=(), docker_status="ok"):
        return CliRunner().invoke(
            click_group_images.images,
            list(arguments),
            obj=FakeApplication(components, images, docker_status),
        )

    return run


@pytest.fixture
def labels(monkeypatch):
    document_commit_label = ConverterCommits.DOCUMENT_COMMIT_LABEL
    pdf_to_markdown_commit_label = ConverterCommits.PDF_TO_MARKDOWN_COMMIT_LABEL
    image_labels = {
        CATALOG_IMAGE: {
            document_commit_label: DOCUMENT_COMMIT,
            pdf_to_markdown_commit_label: STALE_COMMIT,
        },
        CATALOG_IMAGE
        + "-local": {
            document_commit_label: DOCUMENT_COMMIT,
            pdf_to_markdown_commit_label: PDF_TO_MARKDOWN_COMMIT,
        },
        "jejune:hub": {ImageListing.VERSION_LABEL: "1.2.3"},
    }
    monkeypatch.setattr(
        ConverterCommits, "image_labels", lambda image: image_labels.get(image, {})
    )


def converters_component():
    return FakeContComp(
        "converters",
        converter_image_owner=lambda: "catalog",
        handles_document=lambda slug: True,
    )


def hub_component(built=True):
    return FakeContComp(
        "hub",
        image_name="jejune:hub",
        built_image_name=lambda: "jejune:hub" if built else None,
    )


class FakeOtherComponent:
    """A component that is no container; hashable, as the components of the role are
    kept in a set."""

    name = "ecosystem"


def test_images_lists_the_images_when_given_no_subcommand(invoke, labels):
    images = [CATALOG_IMAGE, CATALOG_IMAGE + "-local", "jejune:hub", "other:image"]
    result = invoke([converters_component(), hub_component()], images)
    assert result.exit_code == 0, result.output
    assert (
        result.output
        == invoke([converters_component(), hub_component()], images, ["list"]).output
    )
    lines = [click.unstyle(line) for line in result.output.splitlines()]
    assert lines[0].strip() == "Convert images"
    assert lines[1].split() == [
        "Image",
        "Name",
        "Up-to-date",
        "Document",
        "pdf-to-markdown",
    ]
    assert lines[3].split() == [CATALOG_IMAGE, "✗", "✓", "8e8834c", "✗", "7fe327e"]
    assert lines[4].split() == [
        CATALOG_IMAGE + "-local",
        "✓",
        "✓",
        "8e8834c",
        "✓",
        "8ce4cee",
    ]
    # Two stacked tables
    assert lines[5] == ""
    assert lines[6].strip() == "Other images"
    assert lines[7].split() == ["Image", "Name", "Up-to-date", "Repository"]
    assert lines[9].split() == ["jejune:hub", "1.2.3"]
    assert len(lines) == 10


def test_the_icon_of_the_summary_is_centred_under_its_header(invoke, labels):
    result = invoke([converters_component()], [CATALOG_IMAGE + "-local"])
    lines = [click.unstyle(line) for line in result.output.splitlines()]
    header, row = lines[1], lines[3]
    header_column = header.index("Up-to-date")
    icon_column = row.index("✓")
    assert icon_column == header_column + (len("Up-to-date") - 1) // 2


def test_a_table_is_only_printed_for_the_families_of_the_role(invoke, labels):
    result = invoke([hub_component()], [CATALOG_IMAGE, "jejune:hub"])
    assert "Convert images" not in result.output
    assert "Other images" in result.output
    result = invoke([converters_component()], [CATALOG_IMAGE, "jejune:hub"])
    assert "Convert images" in result.output
    assert "Other images" not in result.output


def test_an_orphan_image_has_a_question_mark(invoke, labels, monkeypatch):
    monkeypatch.setattr(click_group_images, "_catalog_document_names", lambda: set())
    monkeypatch.setattr(
        FakeEcosystem, "discover_doc_repos", lambda *arguments, **options: []
    )
    result = invoke([converters_component()], [CATALOG_IMAGE + "-local"])
    row = click.unstyle(result.output.splitlines()[3])
    assert row.split() == [
        CATALOG_IMAGE + "-local",
        "?",
        "?",
        "8e8834c",
        "✓",
        "8ce4cee",
    ]


def test_no_image_is_told(invoke, labels):
    result = invoke(
        [converters_component(), hub_component(built=False)], ["other:image"]
    )
    assert result.exit_code == 0
    assert "No Docker images of the components of the current role." in result.output


def test_components_which_are_not_containers_are_left_out(invoke, labels):
    result = invoke([FakeOtherComponent()], [CATALOG_IMAGE])
    assert result.exit_code == 0, result.output
    assert "No Docker images" in result.output


def test_docker_missing_is_reported(invoke, labels):
    result = invoke([converters_component()], [], docker_status="error")
    assert result.exit_code == 1
    assert "docker not found on PATH" in result.output
