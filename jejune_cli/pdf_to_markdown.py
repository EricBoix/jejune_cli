import subprocess
import sys
from pathlib import Path

import click
import yaml

from ._env import dot_jejune
from .configuration import print_config_hint, print_config_status


@click.group("pdf-to-markdown", short_help="Test the pipeline across the catalog")
def pdf_to_markdown():
    """Test the pdf-to-markdown pipeline across the document catalog (collection-level)."""


@pdf_to_markdown.command("check-config")
def check_config():
    """Check whether the pdf-to-markdown component is properly configured."""
    print_config_status("pdf-to-markdown")


@pdf_to_markdown.command("hint-config")
def hint_config():
    """Show the configuration hint for the pdf-to-markdown component."""
    print_config_hint("pdf-to-markdown")


@pdf_to_markdown.command("test")
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
    help="Directory holding side-by-side jj_* clones (default: $JEJUNE_ROOT_DIR).",
)
@click.option(
    "--repo",
    default=None,
    help="Run tests for this repository only (by name).",
)
@click.option(
    "--pull/--no-pull",
    default=True,
    show_default=True,
    help="Clone or pull each repository before running tests.",
)
def test_cmd(catalog, root_dir, repo, pull):
    """Run each jj_doc_* Convert/test_main.py suite listed in the catalog.

    Repositories are expected under ROOT_DIR/<name>/.
    Each suite runs inside its own venv (created automatically if absent).
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

    failures: list[str] = []

    for doc in docs:
        name = doc["name"]
        url = doc["url"]
        repo_dir = root / name
        convert_dir = repo_dir / "Convert"

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

        if not convert_dir.exists():
            click.echo(click.style(f"  Convert/ not found in {repo_dir} — skipping.", fg="yellow"))
            failures.append(name)
            continue

        venv_dir = convert_dir / "venv"
        if not venv_dir.exists():
            click.echo("Creating venv ...")
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

        python = venv_dir / "bin" / "python3"

        click.echo("Installing requirements ...")
        req_args = []
        for req in ("requirements.txt", "requirements-dev.txt"):
            if (convert_dir / req).exists():
                req_args += ["-r", req]
        if req_args:
            subprocess.run(
                [str(python), "-m", "pip", "install", "-q"] + req_args,
                cwd=convert_dir,
                check=True,
            )

        click.echo("Running tests ...")
        result = subprocess.run(
            [str(python), "-m", "pytest", "test_main.py", "-v"],
            cwd=convert_dir,
        )
        if result.returncode != 0:
            failures.append(name)

    click.echo()
    if failures:
        click.echo(click.style(f"FAILED: {', '.join(failures)}", fg="red"))
        raise SystemExit(1)
    else:
        click.echo(click.style(f"All {len(docs)} suite(s) passed.", fg="green"))
