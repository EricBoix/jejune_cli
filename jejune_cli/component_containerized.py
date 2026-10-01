"""Containerized component: adds Docker image information."""

import os
from pathlib import Path

import click

from .component_with_config import ConfComp
from .configuration import Configuration
from .containerized_context import ContainerizedContext


class ContComp(ConfComp):
    """Base for components backed by a Docker container.

    Each instance exposes shared infrastructure via ``self._context``
    (a ``ContainerizedContext``).  Subclasses access it as:

      self._context.docker          — comp_command_docker instance
      self._context.docker_daemon   — comp_server_docker_daemon instance
      self._context.coordination    — ContainerCoordination instance
      self._context.git_server      — comp_server_git instance
      self._context.plugin_packages — comp_plugin_packages instance
      self._context.ecosystem       — comp_ecosystem instance

    Built-in subclasses receive the context explicitly via the *context*
    constructor keyword argument.  Plugin subclasses that omit *context* fall
    back to the class-level ``_shared_context`` set by
    ``ContComp.set_shared_context()``, which ``build_components()`` calls
    before any plugin is loaded.
    """

    _shared_context: ContainerizedContext | None = None
    is_external_image: bool = False

    @classmethod
    def set_shared_context(cls, context: ContainerizedContext) -> None:
        """Set the fallback context used by plugin subclasses that omit the context arg."""
        cls._shared_context = context

    def __init__(
        self,
        name: str,
        image_name: str,
        build_context: str = "",
        dockerfile: str | None = None,
        dependencies: list | None = None,
        optional_dependencies: list | None = None,
        configuration: Configuration | None = None,
        hint: str | None = None,
        service_name: str | None = None,
        context: ContainerizedContext | None = None,
    ) -> None:
        ctx = context if context is not None else ContComp._shared_context
        if ctx is None:
            raise RuntimeError(
                "ContainerizedContext not initialised — call build_components() first"
            )
        self._context = ctx
        daemon = ctx.docker_daemon
        deps = (
            ([ctx.docker] if ctx.docker else [])
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
                elif (
                    self._context.plugin_packages is not None
                    and self._context.git_server is not None
                ):
                    repo_name = self._context.plugin_packages.repo_name_for(self.name)
                    ref = f"main:{subpath}" if subpath else None
                    self.build_context = self._context.git_server.remote_git_url(
                        repo_name, ref
                    )
        if not self.build_context:
            return
        click.echo(f"Building {self.image_name} ...")
        self._context.docker.build_image(
            self.image_name,
            self.build_context,
            dockerfile=self.dockerfile,
            no_cache=no_cache,
        )

    def is_built(self) -> bool:
        """Return True if the Docker image named image_name exists locally."""
        if self._context.docker.image_exists(self.image_name):
            return True
        if self.service_name:
            deploy_name = Path(".").resolve().name.lower()
            return self._context.docker.image_exists(
                f"jejune:{deploy_name}-{self.service_name}"
            )
        return False

    @property
    def container_name(self) -> str:
        """Return a Docker-safe container name derived from image_name (no colons)."""
        return self.image_name.replace(":", "_")

    def is_running(self, container_name: str | None = None) -> tuple[bool, str]:
        """Return (running, message) by inspecting the named container."""
        return self._context.docker.is_running(
            container_name if container_name is not None else self.container_name
        )

    def exists(self) -> bool:
        """Return True if the container exists in Docker (running or stopped)."""
        return self._context.docker.container_exists(self.container_name)

    def stop(self) -> None:
        """Stop and remove the Docker container, then unregister it."""
        click.echo(f"Stopping {self.image_name} ...")
        self._context.docker.stop_container(self.container_name)
        self._context.docker.remove_container(self.container_name)
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
        return self._context.coordination.register(
            self.name, self.container_name, **meta
        )

    def register_with_name(self, name_factory, **meta) -> dict:
        """Register this component with a dynamically-named container."""
        return self._context.coordination.register_with_name(
            self.name, name_factory, **meta
        )

    def unregister(self) -> None:
        """Remove this component's container from the jejune registry."""
        self._context.coordination.unregister(self.container_name)

    def json_entries(self) -> list[dict]:
        """Return JSON registry entries for this component."""
        return self._context.coordination.json_for_component(self.name)

    @classmethod
    def image_build_status(cls, components: list) -> "dict[str, bool]":
        """Return {name: is_built()} for every ContComp in *components*."""
        return {
            inst.name: inst.is_built() for inst in components if isinstance(inst, cls)
        }
