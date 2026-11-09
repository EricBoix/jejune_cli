"""Per-document converter utilities for the converters component and click group."""

import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Per-document converter build and test logic
# ---------------------------------------------------------------------------

_DOC_PREFIX = "jejune_doc_"


def _docker_image_name(repo_dir: Path) -> str:
    name = repo_dir.resolve().name
    if name.startswith(_DOC_PREFIX):
        name = name[len(_DOC_PREFIX) :]
    return f"jejune:convert_{name}" if name else "jejune:convert"


def _has_converter(repo_dir: Path) -> tuple[bool, Path, Path]:
    """Return (has_converter, dockerfile, context)."""
    ctx = repo_dir / "DockerContext"
    df = ctx / "Dockerfile"
    return (ctx.is_dir() and df.exists()), df, ctx


def convert_test_doc(
    repo_dir: Path, no_cache: bool, no_build: bool
) -> tuple[str, str, str]:
    """Return (outcome, detail, verbose_output). outcome taken among skipped, build_failed, unchanged or changed."""
    has, dockerfile, context = _has_converter(repo_dir)
    if not has:
        return "skipped", "no DockerContext", ""
    image = _docker_image_name(repo_dir)
    verbose_lines: list[str] = []
    if not no_build:
        extra = ["--no-cache"] if no_cache else []
        build_result = subprocess.run(
            [
                "docker",
                "build",
                *extra,
                "-t",
                image,
                "-f",
                str(dockerfile),
                str(context),
            ],
            capture_output=True,
            text=True,
        )
        verbose_lines.extend(
            (build_result.stdout + build_result.stderr).strip().splitlines()
        )
        if build_result.returncode != 0:
            tail = (build_result.stderr or build_result.stdout).strip().splitlines()
            return (
                "build_failed",
                tail[-1] if tail else "build failed",
                "\n".join(verbose_lines),
            )
    else:
        images_result = subprocess.run(
            ["docker", "images", "-q", image], capture_output=True, text=True
        )
        if not (images_result.returncode == 0 and images_result.stdout.strip()):
            return "build_failed", f"image {image!r} not found", ""
    run_result = subprocess.run(
        ["docker", "run", "--rm", image, "--test"], capture_output=True, text=True
    )
    verbose_lines.extend((run_result.stdout + run_result.stderr).strip().splitlines())
    return (
        ("unchanged", "tests passed", "\n".join(verbose_lines))
        if run_result.returncode == 0
        else ("changed", "tests failed", "\n".join(verbose_lines))
    )
