"""Cross-process coordination for Docker containers managed by jejune."""
import fcntl
import json
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path


class ContainerCoordination:
    """Lightweight bookkeeping layer for Docker containers started by jejune.

    ## Why this exists

    Docker maintains two authoritative registries internally:

    - the *image store* (images pulled or built locally, inspected via
      ``docker images``),
    - the *container store* (running and stopped containers, inspected via
      ``docker inspect``).

    Neither registry knows *which jejune component* owns a given container, nor
    is there a built-in way to enumerate "all containers that belong to this
    tool."  This class fills that gap: it records a mapping of
    (component-name → container-name) in a JSON file
    (~/.jejune/containers.json) whenever jejune starts a detached container,
    and removes the entry when the container is stopped.

    ## Cross-process coordination

    Multiple jejune invocations may run concurrently (e.g. two terminals
    opening separate kg-viewer instances).  To prevent two processes from
    allocating the same container name, every read-modify-write on the JSON
    file is protected by an exclusive POSIX file lock
    (~/.jejune/containers.lock).  Callers never acquire the lock directly;
    all mutating operations go through the methods below.

    ## Relationship with Docker's own registries

    This registry is *complementary* to Docker, not a replacement:

    - Docker is always the source of truth for whether a container actually
      exists or is running (queried via ``comp_command_docker``).
    - This registry answers the higher-level question "which containers did
      jejune intentionally start for component X?" so that list/stop commands
      can scope their operations correctly.
    - Stale entries (container was stopped outside jejune) are benign: the
      next reconcile pass that calls ``comp_command_docker.container_exists()``
      will find them absent and can prune them.
    """

    _REGISTRY = Path.home() / ".jejune" / "containers.json"
    _LOCK = Path.home() / ".jejune" / "containers.lock"

    @contextmanager
    def _registry_lock(self):
        self._LOCK.parent.mkdir(parents=True, exist_ok=True)
        with open(self._LOCK, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            yield

    def _load(self) -> list[dict]:
        if not self._REGISTRY.exists():
            return []
        return json.loads(self._REGISTRY.read_text())

    def _save(self, entries: list[dict]) -> None:
        self._REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        self._REGISTRY.write_text(json.dumps(entries, indent=2))

    def register(self, component: str, container: str, **meta) -> dict:
        """Atomically add a fixed-name container to the registry.

        Use this for components with a single well-known container name (e.g.
        neo4j).  Extra keyword arguments are stored verbatim (e.g. port=8080).
        """
        with self._registry_lock():
            entries = self._load()
            eid = max((e["id"] for e in entries), default=0) + 1
            entry = {"id": eid, "component": component, "container": container, **meta}
            self._save(entries + [entry])
            return entry

    def register_with_name(
        self, component: str, name_factory: Callable[[int], str], **meta
    ) -> dict:
        """Atomically allocate an id, derive the container name, and register.

        name_factory receives the allocated id and returns the container name.
        Both steps happen inside the lock, so two concurrent contexts will
        never derive the same name.  The entry is written before Docker is
        started; if Docker fails the stale entry is removed by the next
        reconcile pass.
        """
        with self._registry_lock():
            entries = self._load()
            eid = max((e["id"] for e in entries), default=0) + 1
            container = name_factory(eid)
            entry = {"id": eid, "component": component, "container": container, **meta}
            self._save(entries + [entry])
            return entry

    def unregister(self, *container_names: str) -> None:
        """Atomically remove registry entries for the given container names."""
        names = set(container_names)
        with self._registry_lock():
            self._save([e for e in self._load() if e["container"] not in names])

    def json_for_component(self, component: str) -> list[dict]:
        """Return entries for *component* from the JSON registry (not live Docker state)."""
        return [e for e in self._load() if e["component"] == component]


CONTAINER_COORDINATION = ContainerCoordination()
