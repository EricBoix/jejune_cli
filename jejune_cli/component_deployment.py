"""Deployment component (internal)."""
import os
import subprocess
from pathlib import Path

from .component_with_config import conf_comp as component
from .component_registry import ComponentRegistry
from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG


class comp_deployment(component):
    def __init__(self) -> None:
        super().__init__(
            name="deployment",
            dependencies=[
                ComponentRegistry().get("catalog"),
            ],
            plugin_deps=["kg-viewer", "md-browser", "docs-server"],
            hint="run `jejune deployment install`",
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
        eco = ComponentRegistry().get("ecosystem")
        env = os.environ.copy()
        root_dir, tmp_dir = eco.resolve_dirs(deploy_dir)
        if root_dir:
            env["JEJUNE_ROOT_DIR"] = str(root_dir)
        for dep in self.dependencies:
            repo_name = PLUGIN_PACKAGE_CATALOG.get(dep.name)
            for subpath, key in getattr(dep, "repos", []):
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

    def generate_docker_compose(self, has_private: bool, name: str, template_dir: Path) -> str:
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

    def build(self, deploy_dir: Path, no_cache: bool = False) -> int:
        if no_cache:
            subprocess.run(["docker", "builder", "prune", "--force"], check=True)
        compose_args = ["build", "--no-cache"] if no_cache else ["build"]
        return self.run_compose(deploy_dir, *compose_args)
