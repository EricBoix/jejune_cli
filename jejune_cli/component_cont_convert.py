"""convert containerized component."""
import os
import subprocess
from pathlib import Path

from .component_containerized import cont_comp
from .configuration import configuration
from .configuration_entry import configuration_entry
from .component_registry import ComponentRegistry


class comp_convert(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="convert",
            image_name="jejune-convert",
            dependencies=[ComponentRegistry().get("pypi-server")],
            hint="run `jejune convert build`",
            configuration=configuration(
                configuration_entry("CONVERT_DOC_DIR",
                    hint="set CONVERT_DOC_DIR in .jejune/env-config",
                    source_file=".jejune/env-config",
                    env_var_validator=self.validate_convert_dir)
            ),
        )

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
            ["docker", "build", *extra, "-t", comp_convert._image_tag(),
             "-f", str(dockerfile), str(context)],
            check=True,
        )

    def check(self) -> tuple[str, str]:
        if self.configuration.check()[0] != "ok":
            return "ok", ""
        built, msg = self.image_built()
        return ("ok", "") if built else ("warn", msg)

    @staticmethod
    def validate_convert_dir(val: str) -> tuple[str, str]:
        """Validate that val points to a Dockerfile or a directory containing DockerContext/."""
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
        base = doc_dir.resolve().parent.parent if doc_dir.is_file() else doc_dir.resolve()
        return f"jejune:convert_{base.name.removeprefix('jejune_doc_')}"

    def is_built(self) -> bool:
        # Override required: self.image_name ("jejune-convert") is a fixed
        # placeholder; the real image name is derived at runtime from
        # CONVERT_DOC_DIR, so we cannot rely on the base-class check.
        return comp_convert._docker.image_exists(comp_convert._image_tag())

    def image_built(self) -> tuple[bool, str]:
        """Return (is_built, message) for the convert Docker image."""
        return (True, "ok") if self.is_built() else (False, "not built")

