"""Containerized component: adds Docker image information."""

import os
from pathlib import Path

import click

from .component_with_config import conf_comp as component
from .configuration import configuration
from .containers_cross_process_coordination import CONTAINER_COORDINATION
from .component_ext_command_docker import DOCKER_COMMAND


class cont_comp(component):
    """Base for components backed by a Docker container.

    build() and is_built() use image_name and build_context.
    Subclasses whose container naming or build process differs override these.
    """

    _coordination = CONTAINER_COORDINATION
    _docker = DOCKER_COMMAND

    def __init__(
        self,
        name: str,
        image_name: str,
        build_context: str = "",
        dockerfile: str | None = None,
        dependencies: list | None = None,
        optional_dependencies: list | None = None,
        configuration: configuration | None = None,
        hint: str | None = None,
        service_name: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            dependencies=[self._docker] + (dependencies or []),
            optional_dependencies=optional_dependencies,
            hint=hint,
            configuration=configuration,
        )
        self.image_name = image_name
        self.build_context = build_context
        self.dockerfile = dockerfile
        self.service_name = service_name

    def build(self, no_cache: bool = False) -> None:
        """Build the Docker image, resolving build_context from self.repos when needed."""
        if not self.build_context:
            repos = getattr(self, "repos", None)
            if repos:
                repo_name, subpath, env_key = repos[0]
                context = os.environ.get(env_key)
                if context:
                    self.build_context = str(Path(context) / subpath) if subpath else context
                else:
                    from .component_registry import REGISTRY
                    ref = f"main:{subpath}" if subpath else None
                    self.build_context = REGISTRY.get("git-server").remote_git_url(repo_name, ref)
        if not self.build_context:
            return
        click.echo(f"Building {self.image_name} ...")
        self._docker.build_image(
            self.image_name, self.build_context,
            dockerfile=self.dockerfile, no_cache=no_cache,
        )

    def is_built(self) -> bool:
        """Return True if the Docker image named image_name exists locally."""
        return self._docker.image_exists(self.image_name)

    @property
    def container_name(self) -> str:
        """Return a Docker-safe container name derived from image_name (no colons)."""
        return self.image_name.replace(":", "_")

    def is_running(self, container_name: str | None = None) -> tuple[bool, str]:
        """Return (running, message) by inspecting the named container."""
        return self._docker.is_running(
            container_name if container_name is not None else self.container_name
        )

    def exists(self) -> bool:
        """Return True if the container exists in Docker (running or stopped)."""
        return self._docker.container_exists(self.container_name)

    def stop(self) -> None:
        """Stop and remove the Docker container, then unregister it."""
        click.echo(f"Stopping {self.image_name} ...")
        self._docker.stop_container(self.container_name)
        self._docker.remove_container(self.container_name)
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

    # --- coordination helpers ---

    def register(self, **meta) -> dict:
        """Add this component's container to the jejune container registry."""
        return self._coordination.register(self.name, self.container_name, **meta)

    def register_with_name(self, name_factory, **meta) -> dict:
        """Register this component with a dynamically-named container."""
        return self._coordination.register_with_name(self.name, name_factory, **meta)

    def unregister(self) -> None:
        """Remove this component's container from the jejune registry."""
        self._coordination.unregister(self.container_name)

    def json_entries(self) -> list[dict]:
        """Return JSON registry entries for this component."""
        return self._coordination.json_for_component(self.name)

    @classmethod
    def register_container(cls, component: str, container: str, **meta) -> dict:
        """Register an external container (e.g. a docker-compose service) by name."""
        return cls._coordination.register(component, container, **meta)

    @classmethod
    def unregister_containers(cls, *names: str) -> None:
        """Unregister multiple containers by name."""
        cls._coordination.unregister(*names)

    @classmethod
    def existing_component_containers(cls) -> list[dict]:
        """Return all cont_comp containers currently present in Docker."""
        from .component_registry import REGISTRY
        return [
            {"component": inst.name, "container": inst.container_name}
            for inst in REGISTRY
            if isinstance(inst, cls) and cls._docker.container_exists(inst.container_name)
        ]
