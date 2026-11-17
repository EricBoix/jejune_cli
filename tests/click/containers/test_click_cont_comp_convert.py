import pytest
from click.testing import CliRunner

from jejune_cli.click.containers import click_cont_comp_convert
from jejune_cli.components.containers.component_cont_convert import CompConvert


class RecordingConvert:
    def __init__(self, built_image_flags=None) -> None:
        self.built_image_flags = built_image_flags
        self.build_arguments = None

    def build(self, **arguments):
        self.build_arguments = arguments

    _image_tag = staticmethod(CompConvert._image_tag)

    def is_built(self, local_documents=None, local_pdf_to_markdown=False):
        return self.built_image_flags == (local_documents, local_pdf_to_markdown)


@pytest.fixture(autouse=True)
def document_directory(monkeypatch, tmp_path):
    document = tmp_path / "jejune_doc_Sample"
    document.mkdir()
    monkeypatch.setenv("CONVERT_DOC_DIR", str(document))


def invoke(convert, command_name, *arguments):
    # The subcommand is invoked on its own: the group would fetch the component
    # from the application context
    command = {
        "build": click_cont_comp_convert.build,
        "run": click_cont_comp_convert.run_cmd,
    }[command_name]
    return CliRunner().invoke(command, list(arguments), obj=convert)


@pytest.mark.parametrize(
    "flags, expected",
    [
        ([], (True, False)),
        (["--no-local-document"], (False, False)),
        (["--local-pdf-to-markdown"], (True, True)),
        (["--no-local-document", "--local-pdf-to-markdown"], (False, True)),
    ],
)
def test_build_flags_select_the_sources(flags, expected):
    convert = RecordingConvert()
    result = invoke(convert, "build", *flags)
    assert result.exit_code == 0, result.output
    assert (
        convert.build_arguments["local_documents"],
        convert.build_arguments["local_pdf_to_markdown"],
    ) == expected


def test_run_looks_for_the_image_of_the_selected_sources():
    convert = RecordingConvert(built_image_flags=(False, True))
    result = invoke(
        convert, "run", "--no-local-document", "--local-pdf-to-markdown", "--test"
    )
    assert "is not built" not in result.output


def test_run_hints_the_build_command_of_the_selected_sources():
    result = invoke(RecordingConvert(), "run", "--no-local-document")
    assert result.exit_code != 0
    assert "jejune convert build --no-local-document" in result.output
