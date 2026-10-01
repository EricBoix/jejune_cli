"""convert containerized component."""

import os
import subprocess
from pathlib import Path

from .component_containerized import ContComp
from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .containerized_context import ContainerizedContext


class comp_convert(ContComp):
    def __init__(
        self, pypi_server, context: ContainerizedContext | None = None
    ) -> None:
        super().__init__(
            name="convert",
            image_name="jejune-convert",
            dependencies=[pypi_server],
            hint="run `jejune convert build`",
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

    def build(self, no_cache: bool = False) -> None:
        if self.configuration.check()[0] != "ok":
            return
        doc_dir = comp_convert._doc_dir()
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
        subprocess.run(
            [
                "docker",
                "build",
                *extra,
                "-t",
                comp_convert._image_tag(),
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
        doc_dir = comp_convert._doc_dir()
        if not doc_dir:
            return "jejune:convert"
        base = (
            doc_dir.resolve().parent.parent if doc_dir.is_file() else doc_dir.resolve()
        )
        return f"jejune:convert_{base.name.removeprefix('jejune_doc_')}"

    def is_built(self) -> bool:
        return self._context.docker.image_exists(comp_convert._image_tag())

    def image_built(self) -> tuple[bool, str]:
        return (True, "ok") if self.is_built() else (False, "not built")
