import importlib.metadata
import subprocess
from pathlib import Path

import click


def version_string() -> str:
    version = importlib.metadata.version("jejune-cli")
    # Now retrieve the SHA:
    # 1. works during development or an editable install where the source tree
    #    is accessible: walks parent dirs looking for a .git folder
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").is_dir():
            try:
                sha = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=candidate,
                ).stdout.strip()
                if sha:
                    return f"{version} ({sha})"
            except Exception:
                pass
            break
    # 2. works after uv tool reinstall where the package lands in e.g.
    #    ~/.local/share/uv/tools/: retrieve the SHA baked by hatch_build.py
    try:
        from ._sha import SHA

        if SHA:
            return f"{version} ({SHA})"
    except ImportError:
        pass
    return f"{version} (SHA not found)"


version_option = click.version_option(version=version_string(), prog_name="jejune")
