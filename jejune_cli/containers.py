"""Central registry for detached Docker containers managed by jejune.

Each entry: {"id": int, "component": str, "container": str, **extra}
The "component" field is the technical mean by which each feature (e.g.
"graph-view") identifies its own containers within the shared registry.

The registry file (~/.jejune/containers.json) is shared across all simultaneous
jejune contexts. A companion lock file (~/.jejune/containers.lock) serialises
every read-modify-write so concurrent instances cannot corrupt the registry.
"""
import fcntl
import json
import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import click

_REGISTRY = Path.home() / ".jejune" / "containers.json"
_LOCK = Path.home() / ".jejune" / "containers.lock"


@contextmanager
def _registry_lock():
    _LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCK, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _load() -> list[dict]:
    if not _REGISTRY.exists():
        return []
    return json.loads(_REGISTRY.read_text())


def _save(entries: list[dict]) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY.write_text(json.dumps(entries, indent=2))


def is_running(name: str) -> bool:
    """Return True if the named Docker container is currently running."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _exists(name: str) -> bool:
    """Return True if the named container exists in Docker (running or stopped)."""
    return subprocess.run(
        ["docker", "inspect", name],
        capture_output=True,
    ).returncode == 0


def register(component: str, container: str, **meta) -> dict:
    """Atomically add a fixed-name container to the registry.

    Use this for components with a single well-known container name (e.g. neo4j).
    Extra keyword arguments are stored verbatim (e.g. port=8080).
    """
    with _registry_lock():
        entries = _load()
        eid = max((e["id"] for e in entries), default=0) + 1
        entry = {"id": eid, "component": component, "container": container, **meta}
        _save(entries + [entry])
        return entry


def register_with_name(
    component: str, name_factory: Callable[[int], str], **meta
) -> dict:
    """Atomically allocate an id, derive the container name, and register.

    name_factory receives the allocated id and returns the container name.
    Both steps happen inside the lock, so two concurrent contexts will never
    derive the same name. The entry is written before Docker is started; if
    Docker fails the stale entry is removed by the next reconcile pass.
    """
    with _registry_lock():
        entries = _load()
        eid = max((e["id"] for e in entries), default=0) + 1
        container = name_factory(eid)
        entry = {"id": eid, "component": component, "container": container, **meta}
        _save(entries + [entry])
        return entry


def unregister(*container_names: str) -> None:
    """Atomically remove registry entries for the given container names."""
    names = set(container_names)
    with _registry_lock():
        _save([e for e in _load() if e["container"] not in names])


def all_entries() -> list[dict]:
    """Return all registry entries, pruning any whose containers have disappeared.

    The prune step is also performed under the lock so concurrent contexts do
    not overwrite each other's reconciliation writes.
    """
    with _registry_lock():
        entries = _load()
        live = [e for e in entries if _exists(e["container"])]
        if len(live) < len(entries):
            _save(live)
        return live


def for_component(component: str) -> list[dict]:
    """Return registry entries for the given component, pruning stale ones."""
    return [e for e in all_entries() if e["component"] == component]


def print_containers_table(prefix: str = "  ") -> None:
    """Print the managed-containers table.

    Called by both `jejune containers list` and `jejune doctor`.
    """
    entries = all_entries()
    if not entries:
        click.echo(f"{prefix}No containers on record.")
        return
    _W_CTR = max(len(e["container"]) for e in entries)
    _W_COMP = max(len(e["component"]) for e in entries)
    header = f"{prefix}{'Container':<{_W_CTR}}  {'Component':<{_W_COMP}}  Port    Status"
    click.echo(header)
    click.echo(prefix + "─" * (len(header) - len(prefix)))
    for entry in entries:
        name = entry["container"]
        comp = entry["component"]
        port = str(entry.get("port", ""))
        running = is_running(name)
        status_str = click.style("running", fg="green") if running else click.style("stopped", fg="yellow")
        click.echo(f"{prefix}{name:<{_W_CTR}}  {comp:<{_W_COMP}}  {port:<6}  {status_str}")


@click.group("containers", short_help="Manage jejune-managed Docker containers")
def containers_cli():
    """Manage Docker containers orchestrated by jejune."""


@containers_cli.command("list")
def containers_list():
    """List all Docker containers managed by jejune with their status."""
    entries = all_entries()
    if not entries:
        click.echo("No containers on record.")
        return
    print_containers_table(prefix="")


@containers_cli.command("exit")
def containers_exit():
    """Stop all detached containers launched by jejune."""
    entries = all_entries()
    if not entries:
        click.echo("No containers on record.")
        return
    for entry in entries:
        name = entry["container"]
        click.echo(f"Stopping {name} ...")
        subprocess.run(["docker", "stop", name], stderr=subprocess.DEVNULL)
    unregister(*(e["container"] for e in entries))
    click.echo(click.style("All containers stopped.", fg="green"))
