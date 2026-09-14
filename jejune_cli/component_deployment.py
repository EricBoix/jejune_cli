"""Deployment component (internal)."""
import os
import subprocess
from pathlib import Path

from .configuration import configuration
from .configuration_entry import configuration_entry
from .component_with_config import conf_comp
from .component_registry import ComponentRegistry


class comp_deployment(conf_comp):
    def __init__(self) -> None:
        self.network = ComponentRegistry().get("network")
        super().__init__(
            name="deployment",
            dependencies=[
                ComponentRegistry().get("catalog"),
                ComponentRegistry().get("docker-daemon"),
                self.network,
            ],
            plugin_deps=["jejune_docs_server", "jejune_kg-graph_viewer", "jejune_markdown_browser"],
            hint="run `jejune build`",
            configuration=configuration(
                configuration_entry("DOCS_SERVER_PORT",      hint="edit deployment.env", source_file="deployment.env"),
                configuration_entry("KG_PORT",               hint="edit deployment.env", source_file="deployment.env"),
                configuration_entry("MARKDOWN_PORT",         hint="edit deployment.env", source_file="deployment.env"),
                configuration_entry("MARKDOWN_TRIGGER_PORT", hint="edit deployment.env", source_file="deployment.env"),
            ),
        )

    def check(self) -> tuple[str, str]:
        for dep in self.dependencies:
            if not dep.is_available():
                return "error", "images not built"
        return "ok", ""

    def is_available(self) -> bool:
        return all(dep.is_available() for dep in self.dependencies)

    @property
    def service_names(self) -> tuple[str, ...]:
        return tuple(dep.service_name for dep in self.dependencies if hasattr(dep, "service_name"))

    def host_ports(self, deploy_dir: Path) -> list[tuple[int, str]]:
        """Return (host_port, env_var_name) pairs after loading deployment.env."""
        self.configuration.load(deploy_dir)
        return [
            (int(val), e.env_var)
            for e in self.configuration
            if (val := os.environ.get(e.env_var))
        ]

    def occupied_host_ports(self, deploy_dir: Path) -> list[tuple[int, str]]:
        """Return host_ports entries whose port is already in use."""
        return [
            (port, var)
            for port, var in self.host_ports(deploy_dir)
            if not self.network.port_free(port)
        ]

    def hint_for_occupied_ports(self, base_dir: Path) -> dict[str, str]:
        """Return {env_var: conflict_hint} for each port in deployment.env already in use."""
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
        return ComponentRegistry().get("catalog").has_private_repos(deploy_dir / "catalog.yaml")

    def generate_docker_compose(self, deploy_dir: Path, template_dir: Path) -> str:
        name = deploy_dir.resolve().name.lower()
        has_private = self.has_private_repos(deploy_dir)
        build_secrets = (
            "      secrets:\n        - catalog\n        - gh_token\n"
            if has_private else
            "      secrets:\n        - catalog\n"
        )
        gh_secret_def = (
            "  gh_token:\n    file: \"${GH_TOKEN_FILE:-~/.github_token}\"\n"
            if has_private else ""
        )
        template = (template_dir / "docker-compose.yml").read_text()
        return (
            template
            .replace("{{NAME}}", name)
            .replace("{{BUILD_SECRETS}}", build_secrets)
            .replace("{{GH_SECRET_DEF}}", gh_secret_def)
        )

    def check_ui_services(self) -> list[tuple[str, bool, str]]:
        from .plugin_registry import PLUGIN_REGISTRY
        from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
        plugins = {p.name: p for p in PLUGIN_REGISTRY.plugins}
        results = []
        for name in PLUGIN_PACKAGE_CATALOG.expected_plugin_names("deployer"):
            p = plugins.get(name)
            ok, msg = p.check_availability() if (p and p.check_availability) else (False, "not installed")
            results.append((name, ok, msg))
        return results

    def _build_env(self, deploy_dir: Path) -> dict:
        from .plugin_registry import PLUGIN_REGISTRY
        eco = ComponentRegistry().get("ecosystem")
        env = os.environ.copy()
        root_dir, tmp_dir = eco.resolve_dirs(deploy_dir)
        if root_dir:
            env["JEJUNE_ROOT_DIR"] = str(root_dir)
        plugins_by_name = {p.name: p for p in PLUGIN_REGISTRY.plugins}
        for dep in self.dependencies:
            repos = getattr(dep, "repos", [])
            if not repos:
                continue
            plugin = plugins_by_name.get(dep.name)
            repo_name = (
                plugin.repo_name
                if plugin and plugin.repo_name
                else PLUGIN_REGISTRY.repo_name_for_plugin(dep.name)
            )
            if repo_name is None:
                continue
            for subpath, key in repos:
                if key:
                    env[key] = eco.resolve(repo_name, root_dir, tmp_dir, subpath)
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
