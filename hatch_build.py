import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


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
