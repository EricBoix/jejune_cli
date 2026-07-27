import subprocess
from pathlib import Path

import click
import yaml

from ._env import dot_jejune


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
    required=True,
    type=click.Path(exists=True),
    help="Directory holding side-by-side jejune_* clones (default: $JEJUNE_ROOT_DIR).",
)
@click.option(
    "--repo",
    default=None,
    help="Operate on this repository only (by name).",
)
@click.option(
    "--pull/--no-pull",
    default=True,
    show_default=True,
    help="Clone or pull each repository.",
)
def test_cmd(catalog, root_dir, repo, pull):
    """Clone or pull each jejune_doc_* repository listed in the catalog.

    Repositories are expected under ROOT_DIR/<name>/.
    """
    if catalog is None:
        default = dot_jejune() / "catalog.yaml"
        if not default.exists():
            raise click.ClickException(
                "No catalog specified. Set $JJ_CATALOG, use --catalog, "
                "or run `jejune configure init` to create .jejune/catalog.yaml."
            )
        catalog = str(default)

    root = Path(root_dir)
    docs = yaml.safe_load(Path(catalog).read_text())["documents"]

    if repo:
        docs = [d for d in docs if d["name"] == repo]
        if not docs:
            raise click.ClickException(f"Repository '{repo}' not found in catalog.")

    for doc in docs:
        name = doc["name"]
        url = doc["url"]
        repo_dir = root / name

        click.echo()
        click.echo(f"{'=' * 60}")
        click.echo(f"  {name}")
        click.echo(f"{'=' * 60}")

        if pull:
            if repo_dir.exists():
                click.echo(f"Pulling {name} ...")
                subprocess.run(["git", "-C", str(repo_dir), "pull"], check=True)
            else:
                click.echo(f"Cloning {name} ...")
                subprocess.run(["git", "-C", str(root), "clone", url], check=True)

    click.echo()
    click.echo(click.style(f"Done ({len(docs)} repo(s)).", fg="green"))
