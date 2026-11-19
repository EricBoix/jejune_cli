"""convert containerized component."""

import os
import re
import subprocess
from pathlib import Path

from jejune_cli.core._package_paths import CatalogConfig, PdfToMarkdownConfig
from jejune_cli.core.component_containerized import ContComp
from jejune_cli.core.configuration import Configuration
from jejune_cli.core.configuration_entry import ConfigurationEntry
from jejune_cli.core.containerized_context import ContainerizedContext
from jejune_cli.components.containers.converter_commits import (
    ConverterCommits,
    ImageCommits,
)
from jejune_cli.components.containers.converter_image_name import ConverterImageName
from jejune_cli.components.containers.converter_sources import (
    ConverterSource,
    ConverterSources,
)


class CompConvert(ContComp):
    def __init__(
        self,
        pypi_server,
        git_access,
        ecosystem,
        context: ContainerizedContext | None = None,
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
        self._ecosystem = ecosystem
        # The Convert/main.py of a document uses pdf-to-markdown: it is a repository
        # of the ecosystem as soon as the document offers such a main.py
        ecosystem.register_repository(
            self.name,
            PdfToMarkdownConfig.REPO_NAME,
            when=self.offers_converter_main,
        )
        ecosystem.register_document_images(self.name, self.image_commits)

    @property
    def image_name(self) -> str:
        """The image of the document of CONVERT_DOC_DIR (it depends on that variable,
        which may be set after the construction of the component)."""
        return CompConvert._image_tag()

    @image_name.setter
    def image_name(self, _value: str) -> None:
        # ContComp.__init__ assigns the placeholder it was given: the image name is
        # always computed from CONVERT_DOC_DIR
        pass

    def image_commits(self, document_name: str) -> ImageCommits:
        """The commits of the document *document_name* and of pdf-to-markdown recorded
        in the image, when it is the document of CONVERT_DOC_DIR and the image is
        built."""
        if document_name != CompConvert._document_name():
            return ImageCommits()
        return ConverterCommits.image_commits(
            self._context.docker, self.image_variants()
        )

    def offers_converter_main(self) -> bool:
        """True when the document of CONVERT_DOC_DIR has a Convert/main.py."""
        doc_dir = CompConvert._doc_dir()
        if not doc_dir:
            return False
        base = doc_dir.parent.parent if doc_dir.is_file() else doc_dir
        return (base / "Convert" / "main.py").is_file()

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
        self,
        no_cache: bool = False,
        token_file: Path | str | None = None,
        local_documents: bool = True,
        local_pdf_to_markdown: bool = False,
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
        image_name = CompConvert._image_tag(local_documents, local_pdf_to_markdown)
        # The local document is the one of CONVERT_DOC_DIR
        document = (
            ConverterSource("cwd", context if doc_dir.is_file() else context.parent)
            if local_documents
            else ConverterSource()
        )
        pdf_to_markdown = (
            ConverterSources.locate_pdf_to_markdown(
                self._ecosystem, self._ecosystem.resolve_dirs()
            )
            if local_pdf_to_markdown
            else ConverterSource()
        )
        ConverterSources.build_image(
            self._context.git_access,
            image_name=image_name,
            dockerfile=dockerfile,
            context_dir=context,
            document=document,
            document_urls=self.dockerfile_git_urls(dockerfile),
            pdf_to_markdown=pdf_to_markdown,
            token_file=token_file,
            no_cache=no_cache,
        )

    @staticmethod
    def container_arguments(
        image: str,
        output_directory: Path | None = None,
        test: bool = False,
        warnings: bool = False,
        debug: bool = False,
        extra_args: tuple[str, ...] = (),
    ) -> list[str]:
        """The `docker run` command of the converter *image*: the pytest run with
        *test*, else the conversion writing in *output_directory* (mounted as
        /output). *warnings* and *debug* are the options of Convert/main.py (debug
        implies warnings there)."""
        if test:
            return ["docker", "run", "--rm", image, "--test", *extra_args]
        if output_directory is None:
            raise ValueError("output_directory is required to convert")
        return [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{output_directory}:/output",
            image,
            "--output_directory",
            "/output",
            *(["--warnings"] if warnings else []),
            *(["--debug"] if debug else []),
            *extra_args,
        ]

    @classmethod
    def run_container(
        cls,
        image: str,
        output_directory: Path | None = None,
        test: bool = False,
        warnings: bool = False,
        debug: bool = False,
        extra_args: tuple[str, ...] = (),
        capture: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run the converter *image* (see container_arguments): its output streams
        to the terminal, or is captured with *capture*."""
        if output_directory is not None:
            output_directory.mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            cls.container_arguments(
                image, output_directory, test, warnings, debug, extra_args
            ),
            capture_output=capture,
            text=capture,
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
    def _document_name() -> str:
        """The name of the document directory of CONVERT_DOC_DIR (empty when unset)."""
        doc_dir = CompConvert._doc_dir()
        if not doc_dir:
            return ""
        return (
            doc_dir.resolve().parent.parent if doc_dir.is_file() else doc_dir.resolve()
        ).name

    @staticmethod
    def _image_tag(
        local_documents: bool = True, local_pdf_to_markdown: bool = False
    ) -> str:
        return ConverterImageName.build(
            ConverterImageName.DOCUMENT_OWNER,
            CompConvert._document_name(),
            local_documents,
            local_pdf_to_markdown,
        )

    def is_built(
        self, local_documents: bool | None = None, local_pdf_to_markdown: bool = False
    ) -> bool:
        """True when the image of the document is built. Without *local_documents*,
        an image built from local sources is as built as the default one."""
        if local_documents is not None:
            return self._context.docker.image_exists(
                CompConvert._image_tag(local_documents, local_pdf_to_markdown)
            )
        return any(
            self._context.docker.image_exists(variant)
            for variant in self.image_variants()
        )

    def image_variants(self) -> list[str]:
        """Every image name of the document of CONVERT_DOC_DIR, whatever its sources."""
        return ConverterImageName.variants(
            ConverterImageName.DOCUMENT_OWNER, CompConvert._document_name()
        )

    def image_built(self) -> tuple[bool, str]:
        return (True, "ok") if self.is_built() else (False, "not built")

    def is_relevant(self, cwd: Path) -> bool:
        """True when the convert command should be visible in the CLI help."""
        return (
            self.configuration.check()[0] == "ok"
            or (cwd / CatalogConfig.REFERENCE_CATALOG).exists()
        )
