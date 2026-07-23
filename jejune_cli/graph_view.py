import json
import os
import shutil
import socket
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import click

_META_URL = "viewer_url"


class _ViewGroup(click.Group):
    """Group that treats an unrecognised first argument as a file URL rather
    than raising 'No such command'."""

    def invoke(self, ctx: click.Context) -> object:
        args = [*ctx._protected_args, *ctx.args]
        if args and self.get_command(ctx, args[0]) is None:
            ctx._protected_args = []
            ctx.args = []
            ctx.meta[_META_URL] = args[0]
        return super().invoke(ctx)


_VIEWER_IMAGE = "jejune:kg_graph_viewer"
_VIEWER_GITHUB = "https://github.com/EricBoix/jejune_kg-graph_viewer.git"
_VIEWER_STACK = Path.home() / ".jejune" / "viewer_stack.json"
_VIEWER_DATA = Path.home() / ".jejune" / "viewer_data"
_VIEWER_NAME_PREFIX = "jejune_kg_viewer_"


def _run(*cmd: str) -> None:
    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _load_stack() -> list[dict]:
    if not _VIEWER_STACK.exists():
        return []
    return json.loads(_VIEWER_STACK.read_text())


def _save_stack(stack: list[dict]) -> None:
    _VIEWER_STACK.parent.mkdir(parents=True, exist_ok=True)
    _VIEWER_STACK.write_text(json.dumps(stack, indent=2))


def _next_id(stack: list[dict]) -> int:
    return max((e["id"] for e in stack), default=0) + 1


def _free_port(start: int = 8080) -> int:
    for port in range(start, 9000):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise click.ClickException("No free port found in range 8080-9000")


def _container_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _build_viewer_image() -> None:
    click.echo(f"Building {_VIEWER_IMAGE} ...")
    viewer_dir = os.environ.get("JEJUNE_KG_VIEWER_DIR")
    if viewer_dir:
        path = Path(viewer_dir).resolve()
        _run(
            "docker", "build",
            "-t", _VIEWER_IMAGE,
            "-f", str(path / "DockerContext" / "Dockerfile"),
            str(path),
        )
    else:
        _run(
            "docker", "build",
            "-t", _VIEWER_IMAGE,
            "-f", "DockerContext/Dockerfile",
            _VIEWER_GITHUB,
        )


def _start_container(viewer_id: int, port: int) -> str:
    container = f"{_VIEWER_NAME_PREFIX}{viewer_id}"
    _run(
        "docker", "run",
        "--rm", "--detach",
        "--name", container,
        "--publish", f"{port}:80",
        "-v", f"{_VIEWER_DATA}:/usr/share/nginx/html/data",
        _VIEWER_IMAGE,
    )
    return container


def _open_browser(url: str) -> None:
    browser = os.environ.get("JEJUNE_BROWSER")
    if browser:
        subprocess.Popen([browser, url])
    else:
        webbrowser.open(url)


def _parse_file_url(url: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        local = Path(parsed.path)
    elif parsed.scheme == "":
        local = Path(url)
    else:
        raise click.ClickException(f"Only local paths and file:// URLs are supported, got: {url!r}")
    local = local.resolve()
    if not local.exists():
        raise click.ClickException(f"File not found: {local}")
    click.echo(f"  {local.as_uri()}")
    return local


@click.group(
    "view",
    cls=_ViewGroup,
    invoke_without_command=True,
    short_help="Visualize a turtle file in the browser",
)
@click.option("--new-server", is_flag=True, help="Start a new viewer container")
@click.option("--list", "list_viewers", is_flag=True, help="List viewer containers")
@click.pass_context
def view(ctx, new_server, list_viewers):
    """Visualize a turtle RDF file (file:// URL) in the browser.

    \b
    jejune graph view path/to/file.ttl
    jejune graph view /path/to/file.ttl
    jejune graph view file:///path/to/file.ttl
    jejune graph view --new-server path/to/file.ttl
    jejune graph view --list
    jejune graph view stop [ID|all]

    Reuses the last running container unless --new-server is given.
    Set JEJUNE_BROWSER to override the browser command.
    Set JEJUNE_KG_VIEWER_DIR to a local clone of jejune_kg-graph_viewer.
    """
    if list_viewers:
        _cmd_list()
        return
    if ctx.invoked_subcommand is not None:
        return
    url = ctx.meta.get(_META_URL)
    if url:
        _cmd_open(url, new_server)
    else:
        click.echo(ctx.get_help())


def _cmd_list() -> None:
    stack = _load_stack()
    if not stack:
        click.echo("No viewer containers on record.")
        return
    for entry in stack:
        name = entry["container"]
        port = entry["port"]
        running = _container_running(name)
        status = click.style("running", fg="green") if running else click.style("stopped", fg="yellow")
        click.echo(f"  id={entry['id']}  {name}  port={port}  {status}")


def _cmd_open(url: str, new_server: bool) -> None:
    local_path = _parse_file_url(url)
    _VIEWER_DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_path, _VIEWER_DATA / local_path.name)

    stack = _load_stack()
    last = next((e for e in reversed(stack) if _container_running(e["container"])), None)

    if new_server or last is None:
        _build_viewer_image()
        viewer_id = _next_id(stack)
        port = _free_port()
        container = _start_container(viewer_id, port)
        stack.append({"id": viewer_id, "container": container, "port": port})
        _save_stack(stack)
        port_used = port
    else:
        port_used = last["port"]

    viewer_url = f"http://localhost:{port_used}/?file={local_path.name}"
    click.echo(f"  {viewer_url}")
    _open_browser(viewer_url)


@view.command("stop")
@click.argument("target", required=False, default=None)
def view_stop(target):
    """Stop viewer container(s).

    TARGET is an integer id or 'all'. Defaults to the last container on the stack.
    """
    stack = _load_stack()
    if not stack:
        click.echo("No viewer containers on record.")
        return

    if target == "all":
        to_stop = stack[:]
    elif target is None:
        to_stop = [stack[-1]]
    else:
        try:
            vid = int(target)
        except ValueError:
            raise click.ClickException(f"Invalid target {target!r}: use an integer id or 'all'")
        to_stop = [e for e in stack if e["id"] == vid]
        if not to_stop:
            raise click.ClickException(f"No viewer with id {vid}")

    for entry in to_stop:
        name = entry["container"]
        click.echo(f"Stopping {name} ...")
        subprocess.run(["docker", "stop", name], stderr=subprocess.DEVNULL)

    remaining = [e for e in stack if e not in to_stop]
    _save_stack(remaining)
