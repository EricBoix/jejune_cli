"""Deployment component (internal)."""
import os
import subprocess
from pathlib import Path

from .component_with_config import conf_comp as component
from .component_registry import ComponentRegistry


class comp_deployment(component):
    def __init__(self) -> None:
        super().__init__(
            name="deployment",
            dependencies=[
                ComponentRegistry().get("catalog"),
                ComponentRegistry().get("docs-server"),
                ComponentRegistry().get("kg-viewer"),
                ComponentRegistry().get("md-browser"),
            ],
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
        from .plugin import _REGISTRY
        from .extensions_registry import _DEPLOYER_CHECK_PACKAGES
        plugins = {p.name: p for p in _REGISTRY}
        results = []
        for _, _, name in _DEPLOYER_CHECK_PACKAGES:
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
            for name, subpath, key in getattr(dep, "repos", []):
                if key:
                    env[key] = eco.resolve(name, root_dir, tmp_dir, subpath)
        return env

    def run_compose(self, deploy_dir: Path, *args: str) -> int:
        result = subprocess.run(
            ["docker", "compose", "--env-file", "deployment.env", *args],
            cwd=deploy_dir,
            env=self._build_env(deploy_dir),
        )
        return result.returncode
