import shutil
import sys
from pathlib import Path

import click

from ._env import dot_jejune
from .configuration import print_config_hint, print_config_status

_TEMPLATES = Path(__file__).parent / "templates"


def _catalog_ref() -> Path:
    """Return the catalog-reference.yaml to use: local .jejune/ if present, else built-in template."""
    local = dot_jejune() / "catalog.yaml"
    return local if local.exists() else _TEMPLATES / "catalog-reference.yaml"


def _do_bootstrap(deployments_dir: Path, deploy_name: str) -> None:
    """Core logic for `jejune deployment configure`."""
    deploy_dir = deployments_dir / f"deploy_{deploy_name}"

    if deploy_dir.exists():
        click.echo(f"Error: {deploy_dir} already exists.", err=True)
        sys.exit(1)

    deploy_dir.mkdir(parents=True)

    shutil.copy(_catalog_ref(), deploy_dir / "catalog.yaml")

    (deploy_dir / "deployment.env").write_text("JJ_CATALOG=./catalog.yaml\n")

    (deploy_dir / "secrets.env").write_text(
        "# Per-developer secrets — never commit this file.\n"
        "JJ_ROOT_DIR=/absolute/path/to/local/clones_CHANGE_ME\n"
        "NEO4J_PASSWORD=your_password_CHANGE_ME\n"
        "LLM_API_KEY=sk-CHANGE_ME\n"
    )

    gitignore = deployments_dir / ".gitignore"
    entry = "**/secrets.env\n"
    if not gitignore.exists() or entry.strip() not in gitignore.read_text().splitlines():
        with gitignore.open("a") as f:
            f.write(entry)

    click.echo(f"Created {deploy_dir}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Edit {deploy_dir}/catalog.yaml — remove unwanted repos, add private ones")
    click.echo(f"  2. Fill in {deploy_dir}/secrets.env with your credentials and JJ_ROOT_DIR")
    click.echo(
        f"  3. git -C {deployments_dir} add"
        f" deploy_{deploy_name}/catalog.yaml"
        f" deploy_{deploy_name}/deployment.env"
        f" .gitignore"
    )
    click.echo(f"  4. git -C {deployments_dir} commit -m 'Add deploy_{deploy_name} deployment'")


@click.group()
def deployment():
    """Manage deployments — collections of active jj_doc_* repositories (collection-level)."""


@deployment.command("check-config")
def check_config():
    """Check whether the deployment component is properly configured."""
    print_config_status("deployment")


@deployment.command("hint-config")
def hint_config():
    """Show the configuration hint for the deployment component."""
    print_config_hint("deployment")


@deployment.command("configure")
@click.argument("deployments_dir", type=click.Path())
@click.argument("deploy_name")
def configure_deployment(deployments_dir, deploy_name):
    """Create a new deployment directory from scaffold files.

    DEPLOYMENTS_DIR is the path to the jj_deployments repository.
    DEPLOY_NAME is the short name for the deployment (creates deploy_DEPLOY_NAME/).

    The deployment catalog is seeded from .jejune/catalog.yaml in the
    current directory if present, otherwise from the built-in template.
    """
    _do_bootstrap(Path(deployments_dir).resolve(), deploy_name)


@deployment.command("list")
@click.argument("deployments_dir", type=click.Path(exists=True))
def list_deployments(deployments_dir):
    """List deployments found in DEPLOYMENTS_DIR."""
    root = Path(deployments_dir)
    dirs = sorted(d for d in root.iterdir() if d.is_dir() and d.name.startswith("deploy_"))
    if not dirs:
        click.echo("No deployments found.")
        return
    for d in dirs:
        catalog = d / "catalog.yaml"
        status = "ok" if catalog.exists() else "missing catalog.yaml"
        click.echo(f"  {d.name}  [{status}]")
