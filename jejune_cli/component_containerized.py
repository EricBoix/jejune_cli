"""Containerized component: adds Docker image information."""

import os
from pathlib import Path

import click

from .component_with_config import conf_comp
from .configuration import configuration as _configuration


class cont_comp(conf_comp):
    """Base for components backed by a Docker container.

    The following class variables are injected by wire_components() before any
    instance is created:
      _docker        — comp_command_docker instance
      _coordination  — ContainerCoordination instance
      _docker_daemon — docker-daemon component instance
      _git_server    — git-server component instance (used in build())
      _plugin_packages       — comp_plugin_packages instance (used in build())
      _ecosystem             — comp_ecosystem instance (available to plugin cont_comp subclasses)
    """

    _docker = None
    _coordination = None
    _docker_daemon = None
    _git_server = None
    _plugin_packages = None
    _ecosystem = None
    is_external_image: bool = False

    def __init__(
        self,
        name: str,
        image_name: str,
        build_context: str = "",
        dockerfile: str | None = None,
        dependencies: list | None = None,
        optional_dependencies: list | None = None,
        configuration: _configuration | None = None,
        hint: str | None = None,
        service_name: str | None = None,
    ) -> None:
        daemon = cont_comp._docker_daemon
        deps = (
            ([cont_comp._docker] if cont_comp._docker else [])
            + ([daemon] if daemon else [])
            + (dependencies or [])
        )
        super().__init__(
            name=name,
            dependencies=deps,
            optional_dependencies=optional_dependencies,
            hint=hint,
            configuration=configuration,
        )
        self.image_name = image_name
        self.build_context = build_context
        self.dockerfile = dockerfile
        self.service_name = service_name

    def docker_env_args(self) -> list[str]:
        """Return [--env KEY=VALUE, ...] for each configured env var present in os.environ."""
        args: list[str] = []
        for e in self.configuration:
            val = os.environ.get(e.env_var)
            if val is not None:
                args += ["--env", f"{e.env_var}={val}"]
        return args

    def build(self, no_cache: bool = False) -> None:
        """Build the Docker image, resolving build_context from self.repos when needed."""
        if not self.build_context:
            repos = getattr(self, "repos", None)
            if repos:
                subpath, env_key = repos[0]
                context = os.environ.get(env_key)
                if context:
                    self.build_context = (
                        str(Path(context) / subpath) if subpath else context
                    )
                elif cont_comp._plugin_packages is not None and cont_comp._git_server is not None:
                    repo_name = cont_comp._plugin_packages.repo_name_for(self.name)
                    ref = f"main:{subpath}" if subpath else None
                    self.build_context = cont_comp._git_server.remote_git_url(
                        repo_name, ref
                    )
        if not self.build_context:
            return
        click.echo(f"Building {self.image_name} ...")
        cont_comp._docker.build_image(
            self.image_name,
            self.build_context,
            dockerfile=self.dockerfile,
            no_cache=no_cache,
        )

    def is_built(self) -> bool:
        """Return True if the Docker image named image_name exists locally."""
        if cont_comp._docker.image_exists(self.image_name):
            return True
        if self.service_name:
            deploy_name = Path(".").resolve().name.lower()
            return cont_comp._docker.image_exists(
                f"jejune:{deploy_name}-{self.service_name}"
            )
        return False

    @property
    def container_name(self) -> str:
        """Return a Docker-safe container name derived from image_name (no colons)."""
        return self.image_name.replace(":", "_")

    def is_running(self, container_name: str | None = None) -> tuple[bool, str]:
        """Return (running, message) by inspecting the named container."""
        return cont_comp._docker.is_running(
            container_name if container_name is not None else self.container_name
        )

    def exists(self) -> bool:
        """Return True if the container exists in Docker (running or stopped)."""
        return cont_comp._docker.container_exists(self.container_name)

    def stop(self) -> None:
        """Stop and remove the Docker container, then unregister it."""
        click.echo(f"Stopping {self.image_name} ...")
        cont_comp._docker.stop_container(self.container_name)
        cont_comp._docker.remove_container(self.container_name)
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
        return cont_comp._coordination.register(self.name, self.container_name, **meta)

    def register_with_name(self, name_factory, **meta) -> dict:
        """Register this component with a dynamically-named container."""
        return cont_comp._coordination.register_with_name(self.name, name_factory, **meta)

    def unregister(self) -> None:
        """Remove this component's container from the jejune registry."""
        cont_comp._coordination.unregister(self.container_name)

    def json_entries(self) -> list[dict]:
        """Return JSON registry entries for this component."""
        return cont_comp._coordination.json_for_component(self.name)

    @classmethod
    def register_container(cls, component: str, container: str, **meta) -> dict:
        """Register an external container (e.g. a docker-compose service) by name."""
        return cls._coordination.register(component, container, **meta)

    @classmethod
    def unregister_containers(cls, *names: str) -> None:
        """Unregister multiple containers by name."""
        cls._coordination.unregister(*names)

    @classmethod
    def image_build_status(cls, components: list) -> "dict[str, bool]":
        """Return {name: is_built()} for every cont_comp in *components*."""
        return {
            inst.name: inst.is_built() for inst in components if isinstance(inst, cls)
        }
