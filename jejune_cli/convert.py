import os
import subprocess
from pathlib import Path

import click

from .configuration import print_config_status

def _doc_dir() -> Path | None:
    val = os.environ.get("CONVERT_DOC_DIR")
    return Path(val) if val else None


def _image_name() -> str:
    d = _doc_dir()
    name = ""
    if d:
        resolved = d.resolve()
        name = (resolved.parent.parent if resolved.is_file() else resolved).name
    for prefix in ("jejune_doc_", "jj_doc_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return f"jejune:convert_{name}" if name else "jejune:convert"


def convert_configured() -> bool:
    """True when CONVERT_DOC_DIR points to an existing Dockerfile or a directory with DockerContext/."""
    d = _doc_dir()
    if d is None:
        return False
    if d.is_file():
        return d.exists()
    return (d / "DockerContext").is_dir()


def image_built() -> tuple[bool, str]:
    """Return (is_built, message) for the convert Docker image."""
    image = _image_name()
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, "not built"
    return True, "ok"


@click.group(short_help="Convert documents via Docker")
def convert():
    """Convert documents using a Docker image built from CONVERT_DOC_DIR/DockerContext/.

    Only appears in `jejune --help` when CONVERT_DOC_DIR is set and the
    DockerContext/ subdirectory exists.  Run `jejune convert check-config`
    to inspect the current configuration status.
    """


@convert.command("check-config")
def check_config():
    """Check whether the convert component is properly configured."""
    print_config_status("convert")


@convert.command("hint-config")
def hint_config():
    """Show the configuration hint for the convert component."""
    val = os.environ.get("CONVERT_DOC_DIR")
    if not val:
        click.echo("set CONVERT_DOC_DIR in .jejune/env-config")
        return
    p = Path(val)
    if p.is_file():
        if not p.exists():
            click.echo(f"Dockerfile not found: {p.resolve()}")
        else:
            click.echo(click.style("no configuration required", fg="green"))
        return
    ctx_path = p / "DockerContext"
    if not ctx_path.is_dir():
        abs_ctx = ctx_path.resolve()
        click.echo(
            f"DockerContext directory not found for CONVERT_DOC_DIR={val}"
            f" (absolute: {abs_ctx})"
        )
        return
    click.echo(click.style("no configuration required", fg="green"))


@convert.command("build")
def build():
    """Build the converter Docker image.

    If CONVERT_DOC_DIR points to a Dockerfile, uses the project root as build
    context (docker build -f <Dockerfile> <project-root>) — for private repos
    whose Dockerfile COPYs local files.  If CONVERT_DOC_DIR points to a
    directory, uses DockerContext/ as the build context — for public repos
    whose Dockerfile clones from GitHub.
    """
    d = _doc_dir()
    if not d:
        raise click.ClickException("CONVERT_DOC_DIR is not set")
    if d.is_file():
        dockerfile = d.resolve()
        context = dockerfile.parent.parent
        if not dockerfile.exists():
            raise click.ClickException(f"Dockerfile not found at {dockerfile}")
    else:
        ctx = d / "DockerContext"
        if not ctx.is_dir():
            raise click.ClickException(f"DockerContext not found at {ctx}")
        dockerfile, context = ctx / "Dockerfile", ctx
    subprocess.run(
        ["docker", "build", "-t", _image_name(), "-f", str(dockerfile), str(context)],
        check=True,
    )


@convert.command(
    "run",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option(
    "--output-dir",
    default="./converted",
    show_default=True,
    help="Host directory mounted as /output inside the container.",
)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def run_cmd(output_dir, extra_args):
    """Run the converter container, forwarding EXTRA_ARGS to the entrypoint."""
    image = _image_name()
    built, _ = image_built()
    if not built:
        raise click.ClickException(
            f"Docker image {image!r} is not built. Run `jejune convert build` first."
        )
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{out}:/output",
            image,
            "--output_directory", "/output",
            *extra_args,
        ],
        check=True,
    )
