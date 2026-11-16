"""Commits recorded in the converter images.

A converter image is labelled with the commit of the document and the commit of
pdf-to-markdown it was built with, so that `ecosystem status` can tell whether they
are the HEAD of their GitHub reference repository. The document clone of the
Dockerfile is pinned to the labelled commit (build argument), otherwise a cached
`git clone` layer would make the label lie.
"""

import json
import re
import subprocess
from pathlib import Path


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

    @staticmethod
    def has_uncommitted_changes(checkout: Path) -> bool:
        """Does *checkout* have modified tracked files? Untracked files are ignored.
        Raises CalledProcessError when it is not a git checkout."""
        return bool(
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(checkout),
                    "status",
                    "--porcelain",
                    "--untracked-files=no",
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )

    @classmethod
    def local_commit(cls, git_access, checkout: Path) -> str | None:
        """The commit SHA of HEAD in *checkout*, suffixed with DIRTY_SUFFIX when it
        has uncommitted changes (None when it is not a git checkout)."""
        try:
            commit = git_access.head_sha(checkout)
            status = subprocess.run(
                ["git", "-C", str(checkout), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
        return commit + cls.DIRTY_SUFFIX if status else commit

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

    @staticmethod
    def is_aligned(commits: list[str], remote_head: str | None) -> bool | None:
        """Are all the *commits* the *remote_head*? None when there is nothing to
        compare."""
        if not commits or remote_head is None:
            return None
        return all(commit == remote_head for commit in commits)
