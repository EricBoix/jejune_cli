import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from jejune_cli import click_cont_comp_converters, component_cont_converters
from jejune_cli.component_cont_converters import CompConverters, ConverterSource

PRIVATE_URL = "https://example.org/team/jejune_doc_Private.git"


@pytest.fixture
def converters(tmp_path, monkeypatch):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(f"RUN git clone {PRIVATE_URL}\n")
    repo_dir = tmp_path / "jejune_doc_Private"
    selection = SimpleNamespace(documents=[{"name": "Private"}], directories=None)
    collection = SimpleNamespace(
        select=lambda *arguments: selection,
        iter_documents=lambda documents, directories: [("Private", "", repo_dir)],
    )
    requested = []

    @contextmanager
    def credentials_file(repository_urls, token_file=None):
        requested.append((repository_urls, token_file))
        yield tmp_path / "credentials"

    instance = CompConverters.__new__(CompConverters)
    instance._catalog_comp = SimpleNamespace(collection=collection)
    instance._context = SimpleNamespace(
        git_access=SimpleNamespace(credentials_file=credentials_file)
    )
    instance._ecosystem = SimpleNamespace(
        locate=lambda name, directories: SimpleNamespace(tier="root")
    )
    instance.has_converter = lambda directory: (True, dockerfile, tmp_path)
    monkeypatch.setattr(
        component_cont_converters.CatalogFile,
        "token_files",
        lambda self: {"Private": "private.access_keys"},
    )
    monkeypatch.setattr(
        component_cont_converters.CatalogFile, "__init__", lambda self, path: None
    )
    monkeypatch.setattr(
        component_cont_converters.CatalogFile, "resolve_path", lambda: tmp_path
    )
    instance.requested = requested
    instance.credentials = tmp_path / "credentials"
    return instance


def test_build_hands_private_credentials_over_as_buildkit_secret(
    converters, monkeypatch
):
    commands = []
    monkeypatch.setattr(
        component_cont_converters.subprocess,
        "run",
        lambda command, check: commands.append(command),
    )
    converters.build()
    assert converters.requested == [([PRIVATE_URL], "private.access_keys")]
    assert (
        "--secret",
        f"id=git_credentials,src={converters.credentials}",
    ) in zip(commands[0], commands[0][1:])


def option_pairs(command, option):
    return [value for key, value in zip(command, command[1:]) if key == option]


def test_default_build_selects_no_local_source_but_labels_the_image(
    converters, monkeypatch
):
    commands = []
    monkeypatch.setattr(
        component_cont_converters.subprocess,
        "run",
        lambda command, check: commands.append(command),
    )
    converters.build()
    assert option_pairs(commands[0], "--build-arg") == []
    assert option_pairs(commands[0], "--build-context") == []
    assert option_pairs(commands[0], "--label") == [
        "jejune.document=git",
        "jejune.pdf-to-markdown=locked",
    ]


def test_local_document_is_copied_and_needs_no_credentials(
    converters, monkeypatch, tmp_path
):
    commands = []
    monkeypatch.setattr(
        component_cont_converters.subprocess,
        "run",
        lambda command, check: commands.append(command),
    )
    converters.build(local_documents=True)
    assert converters.requested == []
    assert "--secret" not in commands[0]
    assert option_pairs(commands[0], "--build-arg") == ["DOC_SOURCE=local"]
    assert option_pairs(commands[0], "--build-context") == [
        f"jejune-doc={tmp_path / 'jejune_doc_Private'}"
    ]
    assert "jejune.document=root:" + str(tmp_path / "jejune_doc_Private") in (
        option_pairs(commands[0], "--label")
    )


def test_local_sources_are_independent_and_both_selectable(tmp_path):
    document = ConverterSource("tmp", tmp_path / "document")
    pdf_to_markdown = ConverterSource("root", tmp_path / "pdf-to-markdown")
    only_pdf_to_markdown = CompConverters.source_arguments(
        ConverterSource(), pdf_to_markdown
    )
    assert option_pairs(only_pdf_to_markdown, "--build-arg") == [
        "PDF_TO_MARKDOWN_SOURCE=local"
    ]
    both = CompConverters.source_arguments(document, pdf_to_markdown)
    assert option_pairs(both, "--build-arg") == [
        "DOC_SOURCE=local",
        "PDF_TO_MARKDOWN_SOURCE=local",
    ]
    assert option_pairs(both, "--label") == [
        f"jejune.document=tmp:{tmp_path / 'document'}",
        f"jejune.pdf-to-markdown=root:{tmp_path / 'pdf-to-markdown'}",
    ]


@pytest.mark.parametrize("tier", ["root", "tmp"])
def test_pdf_to_markdown_found_in_a_tier_is_not_cloned(tier, tmp_path):
    unshallowed = []
    instance = CompConverters.__new__(CompConverters)
    instance._ecosystem = SimpleNamespace(
        locate=lambda name, directories: SimpleNamespace(
            tier=tier, local_path=tmp_path, is_local=True
        ),
        ensure_local=lambda name: pytest.fail("must not clone"),
        unshallow=unshallowed.append,
    )
    assert instance.locate_pdf_to_markdown(None) == ConverterSource(tier, tmp_path)
    # Only the clone managed by jejune_cli (.jejune/tmp) is given its whole history:
    # a checkout of JEJUNE_ROOT_DIR belongs to the user
    assert unshallowed == ([tmp_path] if tier == "tmp" else [])


def test_pdf_to_markdown_found_nowhere_is_cloned_into_tmp_with_its_history(tmp_path):
    cloned = []
    unshallowed = []
    instance = CompConverters.__new__(CompConverters)
    instance._ecosystem = SimpleNamespace(
        locate=lambda name, directories: SimpleNamespace(is_local=False),
        ensure_local=lambda name: cloned.append(name) or tmp_path,
        unshallow=unshallowed.append,
    )
    assert instance.locate_pdf_to_markdown(None) == ConverterSource("tmp", tmp_path)
    assert cloned == ["pdf-to-markdown"]
    assert unshallowed == [tmp_path]


def test_converters_register_pdf_to_markdown_with_the_ecosystem():
    registered = []
    CompConverters(
        docker_daemon=SimpleNamespace(name="docker-daemon"),
        ecosystem=SimpleNamespace(
            register_repository=lambda *arguments: registered.append(arguments)
        ),
        catalog_comp=None,
        context=SimpleNamespace(docker=None, docker_daemon=None),
    )
    assert registered == [("converters", "pdf-to-markdown")]


@pytest.mark.parametrize(
    "returncode, stdout, expected",
    [
        (
            0,
            json.dumps(
                {
                    "jejune.document": "tmp:/a",
                    "jejune.pdf-to-markdown": "root:/b",
                }
            ),
            "document: tmp:/a, pdf-to-markdown: root:/b",
        ),
        (0, "null", "document: git, pdf-to-markdown: locked"),
        (1, "", "document: git, pdf-to-markdown: locked"),
    ],
)
def test_image_source_summary_reads_the_labels(
    returncode, stdout, expected, monkeypatch
):
    monkeypatch.setattr(
        component_cont_converters.subprocess,
        "run",
        lambda command, capture_output, text: SimpleNamespace(
            returncode=returncode, stdout=stdout
        ),
    )
    assert CompConverters.image_source_summary("jejune:convert_X") == expected


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ([], (False, False)),
        (["--local-documents"], (True, False)),
        (["--local-pdf-to-markdown"], (False, True)),
        (["--local"], (True, True)),
    ],
)
def test_local_flag_stands_for_both_local_flags(arguments, expected, monkeypatch):
    class FakeApplication:
        def __init__(self):
            self.built_with = None
            converters = SimpleNamespace(
                build=lambda *build_arguments: setattr(
                    self, "built_with", build_arguments
                )
            )
            self.component_registry = SimpleNamespace(get=lambda name: converters)

    monkeypatch.setattr(click_cont_comp_converters, "AppContext", FakeApplication)
    application = FakeApplication()
    result = CliRunner().invoke(
        click_cont_comp_converters.converters_build, arguments, obj=application
    )
    assert result.exit_code == 0, result.output
    assert application.built_with[-2:] == expected
