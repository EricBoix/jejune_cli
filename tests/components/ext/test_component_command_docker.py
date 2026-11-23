from types import SimpleNamespace

import pytest

from jejune_cli.components.ext import component_ext_command_docker
from jejune_cli.components.ext.component_ext_command_docker import CompCommandDocker


def fake_run(returncode, stdout):
    return lambda command, **options: SimpleNamespace(
        returncode=returncode, stdout=stdout
    )


def test_list_images_gives_repository_and_tag_without_the_untagged_ones(monkeypatch):
    monkeypatch.setattr(
        component_ext_command_docker.subprocess,
        "run",
        fake_run(0, "jejune:hub\n<none>:<none>\noxigraph/oxigraph:latest\n\n"),
    )
    assert CompCommandDocker().list_images() == [
        "jejune:hub",
        "oxigraph/oxigraph:latest",
    ]


@pytest.mark.parametrize("returncode", [1, 125])
def test_list_images_is_empty_when_docker_fails(monkeypatch, returncode):
    monkeypatch.setattr(
        component_ext_command_docker.subprocess,
        "run",
        fake_run(returncode, "jejune:hub\n"),
    )
    assert CompCommandDocker().list_images() == []
