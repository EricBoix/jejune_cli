import os
import subprocess
from pathlib import Path

import click
import yaml

from ._env import dot_jejune

_TMP_PATTERN = ".jejune/tmp/"


def _ensure_gitignored() -> None:
    gitignore = dot_jejune().parent / ".gitignore"
    if gitignore.exists():
        if any(l.strip() == _TMP_PATTERN for l in gitignore.read_text().splitlines()):
            return
        with gitignore.open("a") as f:
            f.write(f"{_TMP_PATTERN}\n")
    else:
        gitignore.write_text(f"{_TMP_PATTERN}\n")


def _tmp_dir() -> Path:
    tmp = dot_jejune() / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    _ensure_gitignored()
    return tmp


@click.command("test")
@click.option(
    "--catalog",
    envvar="JJ_CATALOG",
    default=None,
    type=click.Path(),
    help="Path to a catalog.yaml (default: $JJ_CATALOG, then .jejune/catalog.yaml).",
)
@click.option(
    "--root-dir",
    envvar="JEJUNE_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding side-by-side jejune_* clones (default: $JEJUNE_ROOT_DIR).",
)
@click.option(
    "--repo",
    default=None,
    help="Operate on this repository only (by name).",
)
def test_cmd(catalog, root_dir, repo):
    """List jejune_doc_* repositories found in the catalog.

    Repositories are expected under ROOT_DIR/<name>/. Missing repositories
    (or all when ROOT_DIR is unset) are cloned into .jejune/tmp/ which is
    gitignored automatically.
    """
    if catalog is None:
        default = dot_jejune() / "catalog.yaml"
        if not default.exists():
            raise click.ClickException(
                "No catalog specified. Set $JJ_CATALOG, use --catalog, "
                "or run `jejune configure init` to create .jejune/catalog.yaml."
            )
        catalog = str(default)

    root = Path(root_dir) if root_dir else None
    if root is not None and not root.exists():
        source = "$JEJUNE_ROOT_DIR" if os.environ.get("JEJUNE_ROOT_DIR") == root_dir else "--root-dir"
        raise click.ClickException(f"ROOT_DIR ({source}) does not exist: {root}")

    docs = yaml.safe_load(Path(catalog).read_text())["documents"]

    if repo:
        docs = [d for d in docs if d["name"] == repo]
        if not docs:
            raise click.ClickException(f"Repository '{repo}' not found in catalog.")

    tmp: Path | None = None

    for doc in docs:
        name = doc["name"]
        url = doc["url"]

        repo_dir = root / name if root is not None else None
        if repo_dir is None or not repo_dir.exists():
            if tmp is None:
                tmp = _tmp_dir()
            repo_dir = tmp / name
            if not repo_dir.exists():
                click.echo(f"Cloning {name} ...")
                subprocess.run(["git", "clone", url, str(repo_dir)], check=True)

        present = click.style("present", fg="green") if repo_dir.exists() else click.style("missing", fg="yellow")
        click.echo(f"  {name:<40}  {present}")

    click.echo()
    click.echo(click.style(f"{len(docs)} repo(s).", fg="green"))
