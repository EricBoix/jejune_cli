from types import SimpleNamespace

import pytest

from jejune_cli.component_cont_convert import CompConvert


class RecordingEcosystem:
    def __init__(self):
        self.registrations = []

    def register_repository(self, owner_component_name, repository_name, when=None):
        self.registrations.append((owner_component_name, repository_name, when))


@pytest.fixture
def convert_component():
    ecosystem = RecordingEcosystem()
    component = CompConvert(
        pypi_server=SimpleNamespace(),
        git_access=SimpleNamespace(),
        ecosystem=ecosystem,
        context=SimpleNamespace(docker=None, docker_daemon=None),
    )
    return component, ecosystem


def test_pdf_to_markdown_is_registered_on_the_condition_of_a_converter_main(
    convert_component,
):
    component, ecosystem = convert_component
    assert ecosystem.registrations == [
        ("convert", "pdf-to-markdown", component.offers_converter_main)
    ]


def test_no_converter_main_without_document_directory(convert_component, monkeypatch):
    component, _ = convert_component
    monkeypatch.delenv("CONVERT_DOC_DIR", raising=False)
    assert not component.offers_converter_main()


def test_converter_main_is_looked_for_in_the_document_directory(
    convert_component, monkeypatch, tmp_path
):
    component, _ = convert_component
    monkeypatch.setenv("CONVERT_DOC_DIR", str(tmp_path))
    assert not component.offers_converter_main()
    (tmp_path / "Convert").mkdir()
    (tmp_path / "Convert" / "main.py").write_text("")
    assert component.offers_converter_main()


def test_converter_main_is_looked_for_beside_the_dockerfile_directory(
    convert_component, monkeypatch, tmp_path
):
    component, _ = convert_component
    dockerfile = tmp_path / "DockerContext" / "Dockerfile"
    dockerfile.parent.mkdir()
    dockerfile.write_text("")
    monkeypatch.setenv("CONVERT_DOC_DIR", str(dockerfile))
    assert not component.offers_converter_main()
    (tmp_path / "Convert").mkdir()
    (tmp_path / "Convert" / "main.py").write_text("")
    assert component.offers_converter_main()
