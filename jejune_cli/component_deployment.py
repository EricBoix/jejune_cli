"""Deployment component (internal)."""

import os
import subprocess
from pathlib import Path

from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .component_with_config import ConfComp


class comp_deployment(ConfComp):
    def __init__(
        self,
        network,
        catalog_comp,
        docker_daemon,
        docker_command,
        plugin_registry,
        ecosystem,
    ) -> None:
        self.network = network
        self._docker_command = docker_command
        self._plugin_registry = plugin_registry
        self._ecosystem = ecosystem
        super().__init__(
            name="deployment",
            dependencies=[
                catalog_comp,
                docker_daemon,
                docker_command,
                network,
                ecosystem,
            ],
            plugin_deps=[
                "jejune_docs_server",
                "jejune_kg-graph_viewer",
                "jejune_markdown_browser",
            ],
            hint="run `jejune build`",
            configuration=Configuration(
                ConfigurationEntry(
                    "DOCS_SERVER_PORT",
                    hint="edit deployment.env",
                    source_file="deployment.env",
                ),
                ConfigurationEntry(
                    "KG_PORT", hint="edit deployment.env", source_file="deployment.env"
                ),
                ConfigurationEntry(
                    "MARKDOWN_PORT",
                    hint="edit deployment.env",
                    source_file="deployment.env",
                ),
                ConfigurationEntry(
                    "MARKDOWN_TRIGGER_PORT",
                    hint="edit deployment.env",
                    source_file="deployment.env",
                ),
            ),
        )
        self.cli_name = self.name

    def check(self) -> tuple[str, str]:
        for dep in self.dependencies:
            if not dep.is_available():
                return "error", "images not built"
        return "ok", ""

    def is_available(self) -> bool:
        return all(dep.is_available() for dep in self.dependencies)

    @property
    def service_names(self) -> tuple[str, ...]:
        return tuple(
            dep.service_name
            for dep in self.dependencies
            if hasattr(dep, "service_name")
        )

    def host_ports(self, deploy_dir: Path) -> list[tuple[int, str]]:
        self.configuration.load(deploy_dir)
        return [
            (int(val), e.env_var)
            for e in self.configuration
            if (val := os.environ.get(e.env_var))
        ]

    def occupied_host_ports(self, deploy_dir: Path) -> list[tuple[int, str]]:
        if self.service_names:
            deploy_name = deploy_dir.resolve().name.lower()
            if any(
                self._docker_command.is_running(f"jejune-{deploy_name}-{svc}-1")[0]
                for svc in self.service_names
            ):
                return []
        return [
            (port, var)
            for port, var in self.host_ports(deploy_dir)
            if not self.network.port_free(port)
        ]

    def hint_for_occupied_ports(self, base_dir: Path) -> dict[str, str]:
        result = {}
        for port, var in self.occupied_host_ports(base_dir):
            entry = next(e for e in self.configuration if e.env_var == var)
            src = entry.source_file or "deployment.env"
            result[var] = (
                f"Port {port} is already in use: configure {var} in {src}"
                f" to a different non-conflicting port value"
            )
        return result

    def has_private_repos(self, deploy_dir: Path) -> bool:
        catalog_dep = next((d for d in self.dependencies if d.name == "catalog"), None)
        if catalog_dep is None:
            return False
        return catalog_dep.has_private_repos(deploy_dir / "catalog.yaml")

    def generate_docker_compose(self, deploy_dir: Path, template_dir: Path) -> str:
        name = deploy_dir.resolve().name.lower()
        has_private = self.has_private_repos(deploy_dir)
        build_secrets = (
            "      secrets:\n        - catalog\n        - gh_token\n"
            if has_private
            else "      secrets:\n        - catalog\n"
        )
        gh_secret_def = (
            '  gh_token:\n    file: "${GH_TOKEN_FILE:-~/.github_token}"\n'
            if has_private
            else ""
        )
        template = (template_dir / "docker-compose.yml").read_text()
        return (
            template.replace("{{NAME}}", name)
            .replace("{{BUILD_SECRETS}}", build_secrets)
            .replace("{{GH_SECRET_DEF}}", gh_secret_def)
        )

    def check_ui_services(self) -> list[tuple[str, bool, str]]:
        relevant = [
            p
            for p in self._plugin_registry.plugins
            if self._plugin_registry.repo_name_for_plugin(p.name) in self.plugin_deps
        ]
        return [
            (
                (p.name, *p.check_availability())
                if p.check_availability
                else (p.name, False, "not installed")
            )
            for p in relevant
        ]

    def _build_env(self, deploy_dir: Path) -> dict:
        env = os.environ.copy()
        root_dir, tmp_dir = self._ecosystem.resolve_dirs(deploy_dir)
        if root_dir:
            env["JEJUNE_ROOT_DIR"] = str(root_dir)
        plugins_by_name = {p.name: p for p in self._plugin_registry.plugins}
        for dep in self.dependencies:
            repos = getattr(dep, "repos", [])
            if not repos:
                continue
            plugin = plugins_by_name.get(dep.name)
            repo_name = (
                plugin.repo_name
                if plugin and plugin.repo_name
                else self._plugin_registry.repo_name_for_plugin(dep.name)
            )
            if repo_name is None:
                continue
            for subpath, key in repos:
                if key:
                    env[key] = self._ecosystem.resolve(
                        repo_name, root_dir, tmp_dir, subpath
                    )
        return env

    def run_compose(self, deploy_dir: Path, *args: str) -> int:
        result = subprocess.run(
            ["docker", "compose", "--env-file", "deployment.env", *args],
            cwd=deploy_dir,
            env=self._build_env(deploy_dir),
        )
        return result.returncode

    def build(self, deploy_dir: Path, no_cache: bool = False) -> int:
        if no_cache:
            subprocess.run(["docker", "builder", "prune", "--force"], check=True)
        compose_args = ["build", "--no-cache"] if no_cache else ["build"]
        return self.run_compose(deploy_dir, *compose_args)
