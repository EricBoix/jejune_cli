"""kg-viewer containerized component."""
import shutil
import socket
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import click

from . import containers
from .component_containerized import cont_comp
from .component_registry import ComponentRegistry

_VIEWER_DATA = Path.home() / ".jejune" / "viewer_data"
_VIEWER_NAME_PREFIX = "jejune_kg_viewer_"


class comp_kg_viewer(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="kg-viewer",
            image_name="jejune:kg_graph_viewer",
            dockerfile="DockerContext/Dockerfile",
            service_name="kg-graph-viewer",
            dependencies=[ComponentRegistry().get("ecosystem"), ComponentRegistry().get("docker-command")],
            hint="run `jejune deployment install`",
        )
        self.repos = [("jejune_kg-graph_viewer", None, "KG_GRAPH_VIEWER_CONTEXT")]

    def is_available(self) -> bool:
        return self.is_built()

    def is_running(self) -> tuple[bool, str]:
        deploy_name = Path(".").resolve().name.lower()
        return super().is_running(f"jejune-{deploy_name}-{self.service_name}-1")

    def _adhoc_containers(self) -> list[dict]:
        return containers.json_for_component(self.name)

    def _free_port(self, start: int = 8080) -> int:
        for port in range(start, 9000):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("", port))
                    return port
                except OSError:
                    continue
        raise click.ClickException("No free port found in range 8080-9000")

    def _launch(self, container: str, port: int) -> None:
        result = subprocess.run([
            "docker", "run", "--rm", "--detach",
            "--name", container,
            "--publish", f"{port}:80",
            "-v", f"{_VIEWER_DATA}:/usr/share/nginx/html/data",
            self.image_name,
        ])
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    def _parse_file_url(self, url: str) -> Path:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            local = Path(parsed.path)
        elif parsed.scheme == "":
            local = Path(url)
        else:
            raise click.ClickException(
                f"Only local paths and file:// URLs are supported, got: {url!r}"
            )
        local = local.resolve()
        if not local.exists():
            raise click.ClickException(f"File not found: {local}")
        click.echo(f"  {local.as_uri()}")
        return local

    def _open_browser(self, url: str) -> None:
        browser = os.environ.get("JEJUNE_BROWSER")
        if browser:
            subprocess.Popen([browser, url])
        else:
            webbrowser.open(url)

    def open_view(self, url: str, new_server: bool) -> None:
        local_path = self._parse_file_url(url)
        _VIEWER_DATA.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, _VIEWER_DATA / local_path.name)

        mine = self._adhoc_containers()
        last = next(
            (e for e in reversed(mine) if cont_comp.is_running(self, e["container"])[0]),
            None,
        )

        if new_server or last is None:
            self.build()
            port = self._free_port()
            entry = containers.register_with_name(
                self.name,
                lambda eid: f"{_VIEWER_NAME_PREFIX}{eid}",
                port=port,
            )
            self._launch(entry["container"], port)
            port_used = port
        else:
            port_used = last["port"]

        viewer_url = f"http://localhost:{port_used}/?file={local_path.name}"
        click.echo(f"  {viewer_url}")
        self._open_browser(viewer_url)

    def list_views(self) -> None:
        mine = self._adhoc_containers()
        if not mine:
            click.echo("No viewer containers on record.")
            return
        for entry in mine:
            name = entry["container"]
            port = entry["port"]
            running = cont_comp.is_running(self, name)[0]
            status = (
                click.style("running", fg="green")
                if running
                else click.style("stopped", fg="yellow")
            )
            click.echo(f"  id={entry['id']}  {name}  port={port}  {status}")

    def stop_views(self, target: str | None) -> None:
        mine = self._adhoc_containers()
        if not mine:
            click.echo("No viewer containers on record.")
            return

        if target == "all":
            to_stop = mine
        elif target is None:
            to_stop = [mine[-1]]
        else:
            try:
                vid = int(target)
            except ValueError:
                raise click.ClickException(
                    f"Invalid target {target!r}: use an integer id or 'all'"
                )
            to_stop = [e for e in mine if e["id"] == vid]
            if not to_stop:
                raise click.ClickException(f"No viewer with id {vid}")

        for entry in to_stop:
            name = entry["container"]
            click.echo(f"Stopping {name} ...")
            subprocess.run(["docker", "stop", name], stderr=subprocess.DEVNULL)

        containers.unregister(*(e["container"] for e in to_stop))
