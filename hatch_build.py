import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-reuse-import]


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                cwd=Path(__file__).parent,
            ).stdout.strip()
        except Exception:
            sha = ""
        Path("jejune_cli/_sha.py").write_text(f'SHA = "{sha}"\n')
        build_data["artifacts"].append("jejune_cli/_sha.py")

        pyproject_path = Path(__file__).parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        base = pyproject["tool"]["jejune"]["ecosystem-repo-base"]
        Path("jejune_cli/_ecosystem.py").write_text(
            f'ECOSYSTEM_REPO_BASE = "{base}"\n'
        )
        build_data["artifacts"].append("jejune_cli/_ecosystem.py")
