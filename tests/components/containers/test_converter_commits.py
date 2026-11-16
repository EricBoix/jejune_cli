import json
import subprocess
from types import SimpleNamespace

import pytest

from jejune_cli.components.containers import converter_commits
from jejune_cli.components.containers.converter_commits import ConverterCommits

COMMIT = "e2b9e0a6a3ab7ff6d22706c0257362a29b8bda98"
OTHER_COMMIT = "1" * 40
UV_LOCK = f"""
[[package]]
name = "pdf-to-markdown"
version = "0.1.1.dev43+ge2b9e0a6a"
source = {{ git = "https://github.com/EricBoix/pdf-to-markdown.git#{COMMIT}" }}
dependencies = [
    {{ name = "mdutils" }},
]
"""


class FakeGitAccess:
    def __init__(self, stdout="", returncode=0, error=None):
        self.stdout = stdout
        self.returncode = returncode
        self.error = error

    def ls_remote(self, repository_url, token_file=None, *references, **options):
        if self.error:
            raise self.error
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout)

    def head_sha(self, repo_path):
        return COMMIT


class FakeDocker:
    def __init__(self, existing_images):
        self.existing_images = existing_images

    def image_exists(self, tag):
        return tag in self.existing_images


@pytest.mark.parametrize(
    "git_access, expected",
    [
        (FakeGitAccess(f"{COMMIT}\tHEAD\n"), COMMIT),
        (FakeGitAccess(""), None),
        (FakeGitAccess(returncode=128), None),
        (FakeGitAccess(error=FileNotFoundError("git")), None),
        (FakeGitAccess(error=subprocess.TimeoutExpired("git", 5)), None),
    ],
)
def test_remote_head_is_the_full_sha_or_none(git_access, expected):
    assert ConverterCommits.remote_head(git_access, "https://example.org/x") == expected


@pytest.mark.parametrize(
    "porcelain, expected",
    [("", COMMIT), (" M file.py\n", COMMIT + ConverterCommits.DIRTY_SUFFIX)],
)
def test_local_commit_is_marked_when_the_checkout_is_dirty(
    porcelain, expected, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        converter_commits.subprocess,
        "run",
        lambda command, **options: SimpleNamespace(stdout=porcelain),
    )
    assert ConverterCommits.local_commit(FakeGitAccess(), tmp_path) == expected


def test_local_commit_of_something_that_is_not_a_checkout_is_none(
    monkeypatch, tmp_path
):
    def fail(command, **options):
        raise subprocess.CalledProcessError(128, command)

    monkeypatch.setattr(converter_commits.subprocess, "run", fail)
    assert ConverterCommits.local_commit(FakeGitAccess(), tmp_path) is None


def test_build_arguments_pin_a_cloned_document_and_label_the_commits():
    assert ConverterCommits.build_arguments(COMMIT, True, OTHER_COMMIT) == [
        "--build-arg",
        f"DOC_COMMIT={COMMIT}",
        "--label",
        f"jejune.document-commit={COMMIT}",
        "--label",
        f"jejune.pdf-to-markdown-commit={OTHER_COMMIT}",
    ]
    assert ConverterCommits.build_arguments(COMMIT, False, None) == [
        "--label",
        f"jejune.document-commit={COMMIT}",
    ]
    assert ConverterCommits.build_arguments(None, True, None) == []


@pytest.mark.parametrize(
    "returncode, stdout, expected",
    [
        (0, UV_LOCK, COMMIT),
        (0, UV_LOCK.replace(f"#{COMMIT}", ""), None),
        (0, "", None),
        (1, UV_LOCK, None),
    ],
)
def test_locked_commit_is_read_from_the_uv_lock_of_the_image(
    returncode, stdout, expected, monkeypatch
):
    commands = []

    def run(command, **options):
        commands.append(command)
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    monkeypatch.setattr(converter_commits.subprocess, "run", run)
    assert ConverterCommits.locked_pdf_to_markdown_commit("jejune:image") == expected
    assert commands == [
        ["docker", "run", "--rm", "--entrypoint", "cat", "jejune:image", "uv.lock"]
    ]


def test_labels_are_added_by_building_an_empty_layer_on_top_of_the_image(monkeypatch):
    calls = []
    monkeypatch.setattr(
        converter_commits.subprocess,
        "run",
        lambda command, **options: calls.append((command, options)),
    )
    ConverterCommits.add_labels("jejune:image", {"jejune.key": "value"})
    assert calls == [
        (
            [
                "docker",
                "build",
                "--label",
                "jejune.key=value",
                "-t",
                "jejune:image",
                "-",
            ],
            {"input": "FROM jejune:image\n", "text": True, "check": True},
        )
    ]


@pytest.mark.parametrize(
    "returncode, stdout, expected",
    [
        (
            0,
            json.dumps({"jejune.document-commit": COMMIT}),
            {"jejune.document-commit": COMMIT},
        ),
        (0, "null", {}),
        (1, "", {}),
    ],
)
def test_image_labels(returncode, stdout, expected, monkeypatch):
    monkeypatch.setattr(
        converter_commits.subprocess,
        "run",
        lambda command, **options: SimpleNamespace(
            returncode=returncode, stdout=stdout
        ),
    )
    assert ConverterCommits.image_labels("jejune:image") == expected


def test_labelled_commits_only_look_at_existing_labelled_images(monkeypatch):
    labels = {
        "jejune:built": {"jejune.document-commit": COMMIT},
        "jejune:unlabelled": {},
    }
    monkeypatch.setattr(ConverterCommits, "image_labels", lambda image: labels[image])
    assert ConverterCommits.labelled_commits(
        FakeDocker(["jejune:built", "jejune:unlabelled"]),
        ["jejune:built", "jejune:unlabelled", "jejune:missing"],
        "jejune.document-commit",
    ) == [COMMIT]


@pytest.mark.parametrize(
    "commits, remote_head, expected",
    [
        ([COMMIT], COMMIT, True),
        ([COMMIT, COMMIT], COMMIT, True),
        ([COMMIT, OTHER_COMMIT], COMMIT, False),
        ([COMMIT + ConverterCommits.DIRTY_SUFFIX], COMMIT, False),
        ([], COMMIT, None),
        ([COMMIT], None, None),
    ],
)
def test_alignment_with_the_remote_head(commits, remote_head, expected):
    assert ConverterCommits.is_aligned(commits, remote_head) is expected
