from pathlib import Path
from types import SimpleNamespace

import pytest

from jejune_cli.components.containers.component_cont_convert import CompConvert
from jejune_cli.components.containers.component_cont_converters import CompConverters
from jejune_cli.core.component_containerized import ContComp

# The name docker compose gives to the service `hub` of the project of the directory
COMPOSE_IMAGE = f"jejune:{Path('.').resolve().name.lower()}-hub"


class FakeDocker:
    def __init__(self, existing_images):
        self.existing_images = existing_images

    def image_exists(self, tag):
        return tag in self.existing_images


def container_component(existing_images, service_name=None):
    component = ContComp(
        name="hub",
        image_name="jejune:hub",
        service_name=service_name,
        context=SimpleNamespace(docker=None, docker_daemon=None),
    )
    component._context.docker = FakeDocker(existing_images)
    return component


def test_converters_build_the_catalog_images_of_every_document():
    converters = CompConverters(
        docker_daemon=SimpleNamespace(name="docker-daemon"),
        ecosystem=SimpleNamespace(register_repository=lambda *arguments: None),
        catalog_comp=None,
        context=SimpleNamespace(docker=None, docker_daemon=None),
    )
    assert converters.converter_image_owner() == "catalog"
    assert converters.handles_document("anything")


def test_convert_builds_the_doc_images_of_the_current_document(monkeypatch, tmp_path):
    document_dir = tmp_path / "jejune_doc_Mine"
    document_dir.mkdir()
    monkeypatch.setenv("CONVERT_DOC_DIR", str(document_dir))
    convert = CompConvert(
        pypi_server=SimpleNamespace(),
        git_access=SimpleNamespace(),
        ecosystem=SimpleNamespace(register_repository=lambda *a, **k: None),
        context=SimpleNamespace(docker=None, docker_daemon=None),
    )
    assert convert.converter_image_owner() == "doc"
    assert convert.handles_document("Mine")
    assert not convert.handles_document("Other")


def test_a_component_builds_no_converter_image_by_default():
    component = container_component([])
    assert component.converter_image_owner() is None
    assert not component.handles_document("anything")


@pytest.mark.parametrize(
    "existing_images, service_name, expected",
    [
        (["jejune:hub"], None, "jejune:hub"),
        ([], None, None),
        # Built by docker compose: the name compose gave it
        ([COMPOSE_IMAGE], "hub", COMPOSE_IMAGE),
        ([], "hub", None),
    ],
)
def test_built_image_name_is_the_one_found_locally(
    existing_images, service_name, expected
):
    component = container_component(existing_images, service_name)
    assert component.built_image_name() == expected
    assert component.is_built() == (expected is not None)
