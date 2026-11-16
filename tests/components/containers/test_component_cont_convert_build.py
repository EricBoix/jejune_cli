import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from jejune_cli.components.containers import component_cont_convert
from jejune_cli.components.containers.component_cont_convert import CompConvert
from jejune_cli.components.containers.converter_commits import ConverterCommits
from jejune_cli.components.containers.converter_sources import ConverterSource


class FakeEcosystem:
    def __init__(self, pdf_to_markdown_dir: Path) -> None:
        self.pdf_to_markdown_dir = pdf_to_markdown_dir

    def register_repository(self, *args, **kwargs):
        pass

    def register_document_images(self, *args, **kwargs):
        pass

    def resolve_dirs(self):
        return None


@contextmanager
def no_credentials(urls, token_file):
    yield None


@pytest.fixture
def document_dir(tmp_path, monkeypatch):
    document = tmp_path / "jejune_doc_Sample"
    (document / "DockerContext").mkdir(parents=True)
    (document / "DockerContext" / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.setenv("CONVERT_DOC_DIR", str(document))
    return document


@pytest.fixture
def docker_commands(monkeypatch, tmp_path):
    commands: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    monkeypatch.setattr(ConverterCommits, "remote_head", lambda *args: None)
    monkeypatch.setattr(ConverterCommits, "local_commit", lambda *args: "abc1234")
    monkeypatch.setattr(
        ConverterCommits, "locked_pdf_to_markdown_commit", lambda image: None
    )
    pdf_to_markdown_dir = tmp_path / "pdf-to-markdown"
    monkeypatch.setattr(
        component_cont_convert.ConverterSources,
        "locate_pdf_to_markdown",
        lambda ecosystem, directories: ConverterSource("root", pdf_to_markdown_dir),
    )
    return commands, pdf_to_markdown_dir


def build_component(tmp_path):
    component = CompConvert(
        pypi_server=SimpleNamespace(),
        git_access=SimpleNamespace(),
        ecosystem=FakeEcosystem(tmp_path),
        context=SimpleNamespace(
            docker=None,
            docker_daemon=None,
            git_access=SimpleNamespace(credentials_file=no_credentials),
        ),
    )
    component.configuration.check = lambda: ("ok", "")
    return component


def test_default_build_uses_the_locked_pdf_to_markdown(
    document_dir, docker_commands, tmp_path
):
    commands, _ = docker_commands
    build_component(tmp_path).build()
    command = commands[0]
    assert "--build-context" not in command
    assert "PDF_TO_MARKDOWN_SOURCE=local" not in command
    assert command[command.index("-t") + 1] == "jejune:convert_doc_Sample"


def test_local_pdf_to_markdown_build_selects_the_local_checkout(
    document_dir, docker_commands, tmp_path
):
    commands, pdf_to_markdown_dir = docker_commands
    build_component(tmp_path).build(local_pdf_to_markdown=True)
    command = commands[0]
    assert f"pdf-to-markdown={pdf_to_markdown_dir}" in command
    assert "PDF_TO_MARKDOWN_SOURCE=local" in command
    assert command[command.index("-t") + 1] == "jejune:convert_doc_Sample-local_pdf"
