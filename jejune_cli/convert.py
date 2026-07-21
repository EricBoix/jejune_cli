import os
import subprocess
from pathlib import Path

import click

from .configuration import print_config_status

_IMAGE = "jejuneness:convert"


def _doc_dir() -> Path | None:
    val = os.environ.get("CONVERT_DOC_DIR")
    return Path(val) if val else None


def convert_configured() -> bool:
    """True when CONVERT_DOC_DIR is set and contains a DockerContext/ directory."""
    d = _doc_dir()
    return d is not None and (d / "DockerContext").is_dir()


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
    ctx_path = Path(val) / "DockerContext"
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
    """Build the converter Docker image from CONVERT_DOC_DIR/DockerContext/."""
    d = _doc_dir()
    if not d:
        raise click.ClickException("CONVERT_DOC_DIR is not set")
    ctx = d / "DockerContext"
    if not ctx.is_dir():
        raise click.ClickException(f"DockerContext not found at {ctx}")
    subprocess.run(["docker", "build", "-t", _IMAGE, str(ctx)], check=True)


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
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{out}:/output",
            _IMAGE,
            "--output_directory", "/output",
            *extra_args,
        ],
        check=True,
    )
