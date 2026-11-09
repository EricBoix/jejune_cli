"""convert containerized component."""

import os
import re
import subprocess
from pathlib import Path

from ._package_paths import CatalogConfig
from .component_containerized import ContComp
from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .containerized_context import ContainerizedContext


class CompConvert(ContComp):
    def __init__(
        self, pypi_server, git_access, context: ContainerizedContext | None = None
    ) -> None:
        super().__init__(
            name="convert",
            image_name="jejune-convert",
            dependencies=[pypi_server, git_access],
            hint="run `jejune build` (or `jejune convert build`)",
            configuration=Configuration(
                ConfigurationEntry(
                    "CONVERT_DOC_DIR",
                    hint="set CONVERT_DOC_DIR in .jejune/env-config",
                    source_file=".jejune/env-config",
                    env_var_validator=self.validate_convert_dir,
                )
            ),
            context=context,
        )
        self.cli_name = self.name

    # `git clone` options (some taking a value, e.g. `--depth 1`) precede the URL
    _GIT_CLONE_URL = re.compile(
        r"\bclone(?:\s+(?!https?://)\S+)*\s+(https?://[^\s'\"\\]+)"
    )

    @classmethod
    def dockerfile_git_urls(cls, dockerfile: Path) -> list[str]:
        """Return the URLs of the `git clone` commands found in *dockerfile*."""
        urls: list[str] = []
        for line in dockerfile.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            urls.extend(cls._GIT_CLONE_URL.findall(line))
        return urls

    def repository_urls(self) -> list[str]:
        """Return the `git clone` URLs of the Dockerfile of CONVERT_DOC_DIR."""
        doc_dir = CompConvert._doc_dir()
        if not doc_dir:
            return []
        dockerfile = (
            doc_dir if doc_dir.is_file() else doc_dir / "DockerContext" / "Dockerfile"
        )
        return self.dockerfile_git_urls(dockerfile) if dockerfile.is_file() else []

    def build(
        self, no_cache: bool = False, token_file: Path | str | None = None
    ) -> None:
        if self.configuration.check()[0] != "ok":
            return
        doc_dir = CompConvert._doc_dir()
        if not doc_dir:
            raise ValueError("CONVERT_DOC_DIR is not set")
        if doc_dir.is_file():
            dockerfile = doc_dir.resolve()
            context = dockerfile.parent.parent
            if not dockerfile.exists():
                raise ValueError(f"Dockerfile not found at {dockerfile}")
        else:
            ctx = doc_dir / "DockerContext"
            if not ctx.is_dir():
                raise ValueError(f"DockerContext not found at {ctx}")
            dockerfile, context = ctx / "Dockerfile", ctx
        extra = ["--no-cache"] if no_cache else []
        # The Dockerfile clones private repositories with the credentials handed
        # over as a BuildKit secret: they never end up in an image layer.
        with self._context.git_access.credentials_file(
            self.dockerfile_git_urls(dockerfile), token_file
        ) as credentials:
            secret = (
                ["--secret", f"id=git_credentials,src={credentials}"]
                if credentials
                else []
            )
            subprocess.run(
                [
                    "docker",
                    "build",
                    *extra,
                    *secret,
                    "-t",
                    CompConvert._image_tag(),
                    "-f",
                    str(dockerfile),
                    str(context),
                ],
                check=True,
            )

    def check(self) -> tuple[str, str]:
        if self.configuration.check()[0] != "ok":
            return "ok", ""
        built, msg = self.image_built()
        return ("ok", "") if built else ("error", msg)

    @staticmethod
    def validate_convert_dir(val: str) -> tuple[str, str]:
        path = Path(val)
        if path.is_file():
            if not path.exists():
                return "error", f"Dockerfile not found at {path.resolve()}"
            return "ok", ""
        ctx = path / "DockerContext"
        if not ctx.is_dir():
            return "error", f"DockerContext not found at {ctx}"
        return "ok", ""

    @staticmethod
    def _doc_dir() -> Path | None:
        val = os.environ.get("CONVERT_DOC_DIR")
        return Path(val) if val else None

    @staticmethod
    def _image_tag() -> str:
        doc_dir = CompConvert._doc_dir()
        if not doc_dir:
            return "jejune:convert"
        base = (
            doc_dir.resolve().parent.parent if doc_dir.is_file() else doc_dir.resolve()
        )
        return f"jejune:convert_{base.name.removeprefix('jejune_doc_')}"

    def is_built(self) -> bool:
        return self._context.docker.image_exists(CompConvert._image_tag())

    def image_built(self) -> tuple[bool, str]:
        return (True, "ok") if self.is_built() else (False, "not built")

    def is_relevant(self, cwd: Path) -> bool:
        """True when the convert command should be visible in the CLI help."""
        return (
            self.configuration.check()[0] == "ok"
            or (cwd / CatalogConfig.FULL_CATALOG).exists()
        )
