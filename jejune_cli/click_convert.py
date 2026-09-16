import subprocess
import sys
from pathlib import Path

import click

from .click_comp_configuration import print_config_check, print_config_status


@click.group(short_help="Convert documents via Docker")
@click.pass_context
def convert(ctx):
    """Convert documents using a Docker image built from CONVERT_DOC_DIR/DockerContext/.

    Only appears in `jejune --help` when CONVERT_DOC_DIR is set and the
    DockerContext/ subdirectory exists.  Run `jejune convert check-config`
    to inspect the current configuration status.
    """
    from .component_registry import REGISTRY as COMP_REGISTRY
    ctx.obj = COMP_REGISTRY.get("convert")


@convert.command("check-config")
@click.pass_obj
def check_config(conv):
    """Show per-variable configuration detail for the convert component."""
    print_config_check(conv.configuration)


@convert.command("status-config")
@click.pass_obj
def status_config(conv):
    """Show convert configuration status."""
    print_config_status(conv.configuration)


@convert.command("hint-config")
@click.pass_obj
def hint_config(conv):
    """Show the configuration hint for the convert component."""
    doc_dir = conv._doc_dir()
    if not doc_dir:
        click.echo("set CONVERT_DOC_DIR in .jejune/env-config")
        return
    status, msg = conv.validate_convert_dir(str(doc_dir))
    if status == "error":
        click.echo(msg)
    else:
        click.echo(click.style("no configuration required", fg="green"))


@convert.command("check-availability")
@click.pass_obj
def check_availability(conv):
    """Show detailed convert availability (image name and build status)."""
    built, msg = conv.image_built()
    image = conv._image_tag()
    label = click.style("built", fg="green") if built else click.style(msg, fg="yellow")
    click.echo(f"  image   {image}")
    click.echo(f"  status  {label}")


@convert.command("status-availability")
@click.pass_obj
def status_availability(conv):
    """Show convert availability status."""
    built, msg = conv.image_built()
    if built:
        click.echo(f"convert: {click.style('ok', fg='green')}")
    else:
        click.echo(f"convert: {click.style(msg, fg='yellow')}")


@convert.command("hint-availability")
@click.pass_obj
def hint_availability(conv):
    """Show how to build the convert image if it is not built."""
    built, _ = conv.image_built()
    if built:
        click.echo(click.style("convert image is built", fg="green"))
    else:
        click.echo("run `jejune convert build`")


@convert.command("build")
@click.option("--no-cache", is_flag=True, default=False,
              help="Do not use Docker layer cache when building.")
@click.pass_obj
def build(conv, no_cache: bool):
    """Build the converter Docker image.

    If CONVERT_DOC_DIR points to a Dockerfile, uses the project root as build
    context (docker build -f <Dockerfile> <project-root>) — for private repos
    whose Dockerfile COPYs local files.  If CONVERT_DOC_DIR points to a
    directory, uses DockerContext/ as the build context — for public repos
    whose Dockerfile clones from GitHub.
    """
    try:
        click.echo(f"Building {conv._image_tag()} ...")
        conv.build(no_cache=no_cache)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


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
@click.option(
    "--test",
    is_flag=True,
    default=False,
    help="Run container tests (pytest) instead of converting.",
)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def run_cmd(conv, output_dir, test, extra_args):
    """Run the converter container, forwarding EXTRA_ARGS to the entrypoint."""
    image = conv._image_tag()
    built, _ = conv.image_built()
    if not built:
        raise click.ClickException(
            f"Docker image {image!r} is not built. Run `jejune convert build` first."
        )
    if test:
        result = subprocess.run(
            ["docker", "run", "--rm", image, "--test", *extra_args],
        )
    else:
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{out}:/output",
                image,
                "--output_directory", "/output",
                *extra_args,
            ],
        )
    sys.exit(result.returncode)
