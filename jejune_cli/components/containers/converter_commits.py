"""Commits recorded in the converter images.

A converter image is labelled with the commit of the document and the commit of
pdf-to-markdown it was built with, so that `ecosystem status` can tell whether they
are the ones of the sources the ecosystem designates now. The document clone of the
Dockerfile is pinned to the labelled commit (build argument), otherwise a cached
`git clone` layer would make the label lie.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ImageAlignment(Enum):
    """Is a converter image built from the sources the ecosystem designates now?
    UNKNOWN is "maybe": it cannot be told from the commits."""

    ALIGNED = "aligned"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ImageCommits:
    """The commits recorded in the built image(s) of a document: one per image (and
    per input) that is labelled with one."""

    document: list[str] = field(default_factory=list)
    pdf_to_markdown: list[str] = field(default_factory=list)


class ConverterCommits:
    # Image labels recording where the inputs of an image came from
    DOCUMENT_SOURCE_LABEL = "jejune.document"
    PDF_TO_MARKDOWN_SOURCE_LABEL = "jejune.pdf-to-markdown"
    # Image labels recording the commits of the inputs of an image
    DOCUMENT_COMMIT_LABEL = "jejune.document-commit"
    PDF_TO_MARKDOWN_COMMIT_LABEL = "jejune.pdf-to-markdown-commit"
    # Build argument of the Dockerfile of every document: commit to check out
    DOCUMENT_COMMIT_ARGUMENT = "DOC_COMMIT"
    # Appended to the commit of a checkout with uncommitted changes: such a commit
    # is never the one of a remote HEAD
    DIRTY_SUFFIX = "-dirty"
    # Untracked files of this kind make a checkout dirty (the other ones do not)
    PYTHON_SOURCE_SUFFIX = ".py"
    UNTRACKED_STATUS = "??"
    LOCKED_COMMIT_PATTERN = re.compile(
        r'name = "pdf-to-markdown"\s+version = "[^"]*"\s+'
        r'source = \{ git = "[^"#]*#([0-9a-f]{40})" \}'
    )

    @staticmethod
    def remote_head(
        git_access,
        repository_url: str,
        token_file: Path | str | None = None,
        **run_options,
    ) -> str | None:
        """The full commit SHA of the remote HEAD of *repository_url* (None when it
        cannot be reached or is empty). Network call: authentication is delegated to
        git-access."""
        try:
            completed = git_access.ls_remote(
                repository_url, token_file, "HEAD", **run_options
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        # ls-remote output: "<SHA>\tHEAD" (nothing for an empty repository)
        return completed.stdout.strip().split("\t")[0] or None

    @classmethod
    def has_uncommitted_changes(cls, checkout: Path) -> bool:
        """Does *checkout* have modified tracked files or untracked Python source
        files (those ignored by git do not count)? The other untracked files are
        ignored. Raises CalledProcessError when it is not a git checkout."""
        status = subprocess.run(
            [
                "git",
                "-C",
                str(checkout),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return any(cls._is_uncommitted(line) for line in status.splitlines() if line)

    @classmethod
    def _is_uncommitted(cls, status_line: str) -> bool:
        """Does this line of `git status --porcelain` make a checkout dirty?"""
        if not status_line.startswith(cls.UNTRACKED_STATUS):
            return True
        # A path with special characters is quoted; in doubt, it is dirty
        untracked_path = status_line[len(cls.UNTRACKED_STATUS) :].strip().strip('"')
        return not untracked_path or untracked_path.endswith(cls.PYTHON_SOURCE_SUFFIX)

    @classmethod
    def local_commit(cls, git_access, checkout: Path) -> str | None:
        """The commit SHA of HEAD in *checkout*, suffixed with DIRTY_SUFFIX when it
        has uncommitted changes (None when it is not a git checkout)."""
        try:
            commit = git_access.head_sha(checkout)
            dirty = cls.has_uncommitted_changes(checkout)
        except (OSError, subprocess.CalledProcessError):
            return None
        return commit + cls.DIRTY_SUFFIX if dirty else commit

    @classmethod
    def build_arguments(
        cls,
        document_commit: str | None,
        pin_document: bool,
        pdf_to_markdown_commit: str | None,
    ) -> list[str]:
        """The `docker build` arguments recording the commits (and, for a document
        cloned by the Dockerfile, pinning the clone to its commit)."""
        arguments: list[str] = []
        if document_commit:
            if pin_document:
                arguments += [
                    "--build-arg",
                    f"{cls.DOCUMENT_COMMIT_ARGUMENT}={document_commit}",
                ]
            arguments += ["--label", f"{cls.DOCUMENT_COMMIT_LABEL}={document_commit}"]
        if pdf_to_markdown_commit:
            arguments += [
                "--label",
                f"{cls.PDF_TO_MARKDOWN_COMMIT_LABEL}={pdf_to_markdown_commit}",
            ]
        return arguments

    @classmethod
    def locked_pdf_to_markdown_commit(cls, image: str) -> str | None:
        """The pdf-to-markdown commit locked by the uv.lock inside *image* (None when
        the lock does not name one, e.g. for a local pdf-to-markdown)."""
        completed = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "cat", image, "uv.lock"],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return None
        match = cls.LOCKED_COMMIT_PATTERN.search(completed.stdout)
        return match.group(1) if match else None

    @staticmethod
    def add_labels(image: str, labels: dict[str, str]) -> None:
        """Add *labels* to *image*: a build of an empty layer on top of it."""
        arguments = [
            argument
            for key, value in labels.items()
            for argument in ("--label", f"{key}={value}")
        ]
        subprocess.run(
            ["docker", "build", *arguments, "-t", image, "-"],
            input=f"FROM {image}\n",
            text=True,
            check=True,
        )

    @staticmethod
    def image_labels(image: str) -> dict[str, str]:
        """The labels of *image* (none when it cannot be inspected)."""
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Labels}}", image],
            capture_output=True,
            text=True,
        )
        if inspected.returncode != 0:
            return {}
        return json.loads(inspected.stdout) or {}

    @classmethod
    def labelled_commits(cls, docker, images: list[str], label: str) -> list[str]:
        """The *label* commit of every existing image of *images* that has one."""
        return [
            labels[label]
            for image in images
            if docker.image_exists(image)
            for labels in [cls.image_labels(image)]
            if label in labels
        ]

    @classmethod
    def image_commits(cls, docker, images: list[str]) -> ImageCommits:
        """The commits of the document and of pdf-to-markdown recorded in the
        existing *images*."""
        return ImageCommits(
            document=cls.labelled_commits(docker, images, cls.DOCUMENT_COMMIT_LABEL),
            pdf_to_markdown=cls.labelled_commits(
                docker, images, cls.PDF_TO_MARKDOWN_COMMIT_LABEL
            ),
        )

    @classmethod
    def compare(cls, image_commit: str, current_commit: str | None) -> ImageAlignment:
        """Is *image_commit* (recorded in an image) the *current_commit* of the
        source the ecosystem designates? Unknown when that commit is not known, and
        when both are the same dirty commit: the uncommitted changes may differ."""
        if current_commit is None:
            return ImageAlignment.UNKNOWN
        if image_commit != current_commit:
            return ImageAlignment.MISALIGNED
        if image_commit.endswith(cls.DIRTY_SUFFIX):
            return ImageAlignment.UNKNOWN
        return ImageAlignment.ALIGNED

    @staticmethod
    def combine(verdicts: list[ImageAlignment]) -> ImageAlignment | None:
        """The verdict of an image from those of its inputs: a known difference
        prevails, then an unknown one. None when there is nothing to combine."""
        if not verdicts:
            return None
        for verdict in (ImageAlignment.MISALIGNED, ImageAlignment.UNKNOWN):
            if verdict in verdicts:
                return verdict
        return ImageAlignment.ALIGNED
