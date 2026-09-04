"""Containerized component: adds Docker image information."""

import subprocess

import click

from .component_internal import component
from .configuration import configuration


class cont_comp(component):
    """Base for components backed by a Docker container.

    build() and is_built() use image_name and build_context.
    Subclasses whose container naming or build process differs override these.
    """

    def __init__(
        self,
        name: str,
        image_name: str,
        build_context: str = "",
        dependencies: list[str] | None = None,
        optional_dependencies: list[str] | None = None,
        configuration: configuration | None = None,
        hint: str | None = None,
        service_name: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            dependencies=dependencies,
            optional_dependencies=optional_dependencies,
            hint=hint,
            configuration=configuration,
        )
        self.image_name = image_name
        self.build_context = build_context
        self.service_name = service_name

    def build(self, no_cache: bool = False) -> None:
        """Build the Docker image from build_context. No-op when build_context is empty."""
        if not self.build_context:
            return
        click.echo(f"Building {self.image_name} ...")
        extra = ["--no-cache"] if no_cache else []
        result = subprocess.run(
            ["docker", "build", *extra, "-t", self.image_name, self.build_context]
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    def is_built(self) -> bool:
        """Return True if the Docker image named image_name exists locally."""
        r = subprocess.run(
            ["docker", "images", "-q", self.image_name],
            capture_output=True,
            text=True,
        )
        return bool(r.returncode == 0 and r.stdout.strip())

    @property
    def container_name(self) -> str:
        """Return a Docker-safe container name derived from image_name (no colons)."""
        return self.image_name.replace(":", "_")

    def is_running(self, container_name: str | None = None) -> tuple[bool, str]:
        """Return (running, message) by inspecting the named container."""
        name = container_name if container_name is not None else self.container_name
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip() == "true":
            return True, "ok"
        return False, "not started"

    def exists(self) -> bool:
        """Return True if the container exists in Docker (running or stopped)."""
        return (
            subprocess.run(
                ["docker", "inspect", self.container_name],
                capture_output=True,
            ).returncode
            == 0
        )

    def register(self, **meta) -> dict:
        """Add this component's container to the jejune container registry."""
        from . import containers as _c

        return _c.register(self.name, self.container_name, **meta)

    def register_with_name(self, name_factory, **meta) -> dict:
        """Register this component with a dynamically-named container."""
        from . import containers as _c

        return _c.register_with_name(self.name, name_factory, **meta)

    def unregister(self) -> None:
        """Remove this component's container from the jejune registry."""
        from . import containers as _c

        _c.unregister(self.container_name)

    def stop(self) -> None:
        """Stop and remove the Docker container, then unregister it."""
        click.echo(f"Stopping {self.image_name} ...")
        subprocess.run(["docker", "stop", self.container_name], stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "rm", self.container_name], stderr=subprocess.DEVNULL)
        self.unregister()
        click.echo(f"{self.image_name} stopped.")

    def delete(self) -> None:
        """Stop the container if running, then unregister."""
        running, _ = self.is_running()
        if running:
            self.stop()
        else:
            self.unregister()

    def check(self) -> tuple[str, str]:
        ok, msg = self.is_running()
        return ("ok", "") if ok else ("error", msg)
