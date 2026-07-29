"""UI deployment commands — attached to the `deployment` group by deployment.py."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
import yaml

_TEMPLATES = Path(__file__).parent / "templates"
_T_UI = _TEMPLATES / "deployer" / "ui-deployment"

_UI_SERVICES = ("docs-server", "kg-graph-viewer", "markdown-browser")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_catalog_path(deployments_dir: Path) -> Path | None:
    """Locate full-catalog.yaml in the sibling jejune_catalog repo."""
    candidate = deployments_dir.parent / "jejune_catalog" / "full-catalog.yaml"
    return candidate if candidate.exists() else None


def _has_private_repos(catalog_path: Path) -> bool:
    data = yaml.safe_load(catalog_path.read_text()) or {}
    return any(not doc.get("public", True) for doc in data.get("documents", []))


def _docker_compose_content(has_private: bool, name: str) -> str:
    build_secrets = (
        "      secrets:\n        - catalog\n        - gh_token\n"
        if has_private else
        "      secrets:\n        - catalog\n"
    )
    gh_secret_def = (
        "  gh_token:\n    file: \"${GH_TOKEN_FILE:-~/.github_token}\"\n"
        if has_private else ""
    )
    template = (_T_UI / "docker-compose.yml").read_text()
    return (
        template
        .replace("{{NAME}}", name)
        .replace("{{BUILD_SECRETS}}", build_secrets)
        .replace("{{GH_SECRET_DEF}}", gh_secret_def)
    )


def _resolve_deploy_dir(deployments_dir: str, name: str) -> Path:
    return Path(deployments_dir).resolve() / name


def _run_compose(deploy_dir: Path, *args: str) -> None:
    from .ecosystem import DEPLOYER_REPOS, resolve

    env = os.environ.copy()
    raw_root = env.get("JEJUNE_ROOT_DIR")
    root_dir = Path(raw_root).resolve() if raw_root else None
    if root_dir:
        env["JEJUNE_ROOT_DIR"] = str(root_dir)

    tmp_dir = deploy_dir.resolve() / ".jejune" / "tmp"
    if not tmp_dir.is_dir():
        tmp_dir = None

    for name, subpath, key in DEPLOYER_REPOS:
        if key:
            env[key] = resolve(name, root_dir, tmp_dir, subpath)

    result = subprocess.run(
        ["docker", "compose", "--env-file", "deployment.env", *args],
        cwd=deploy_dir,
        env=env,
    )
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@click.command("ui-configure")
@click.argument("deployments_dir", type=click.Path())
@click.argument("name")
def ui_configure(deployments_dir, name):
    """Scaffold a new UI deployment directory NAME in DEPLOYMENTS_DIR.

    Creates catalog.yaml (seeded from the sibling jejune_docs_server repo's
    full-catalog.yaml when available), docker-compose.yml, and deployment.env.
    A .gitignore and secrets.env.template are added only when the catalog
    contains private repositories.
    """
    deployments_dir = Path(deployments_dir)
    deploy_dir = deployments_dir / name

    if deploy_dir.exists():
        click.echo(f"Error: {deploy_dir} already exists.", err=True)
        sys.exit(1)

    deploy_dir.mkdir(parents=True)
    dot_jejune = deploy_dir / ".jejune"
    dot_jejune.mkdir()
    shutil.copy(_T_UI / "role", dot_jejune / "role")
    (dot_jejune / "origin").write_text(f"{deploy_dir}\n")

    full_catalog = _full_catalog_path(deployments_dir)
    if full_catalog:
        shutil.copy(full_catalog, deploy_dir / "catalog.yaml")
        click.echo(f"Seeded catalog.yaml from {full_catalog}")
    else:
        shutil.copy(_TEMPLATES / "catalog-curator" / "trivial-catalog.yaml", deploy_dir / "catalog.yaml")
        click.echo("Seeded catalog.yaml from built-in template — populate manually.")

    has_private = _has_private_repos(deploy_dir / "catalog.yaml")
    (deploy_dir / "docker-compose.yml").write_text(_docker_compose_content(has_private, name))
    shutil.copy(_T_UI / "deployment.env", deploy_dir / "deployment.env")

    if has_private:
        (deploy_dir / ".gitignore").write_text("secrets.env\n")
        shutil.copy(_T_UI / "secrets.env.template", deploy_dir / "secrets.env.template")

    click.echo(f"Created {deploy_dir}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Review {deploy_dir}/catalog.yaml")
    click.echo(f"  2. Adjust ports in {deploy_dir}/deployment.env if needed")
    step = 3
    if has_private:
        click.echo(f"  {step}. Copy secrets.env.template → secrets.env and fill in GH_TOKEN_FILE")
        step += 1
    click.echo(f"  {step}. Build:  jejune build")
    click.echo(f"  {step + 1}. Start:  jejune up")


@click.command("list")
@click.argument("deployments_dir", type=click.Path(exists=True))
def ui_list(deployments_dir):
    """List deployments (directories with docker-compose.yml) in DEPLOYMENTS_DIR."""
    root = Path(deployments_dir)
    dirs = sorted(
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("deploy_") and (d / "docker-compose.yml").exists()
    )
    if not dirs:
        click.echo("No UI deployments found.")
        return
    for d in dirs:
        has_catalog = (d / "catalog.yaml").exists()
        status = "ok" if has_catalog else "missing catalog.yaml"
        click.echo(f"  {d.name}  [{status}]")


def _deployment_dir(deploy_dir_name: str | None) -> Path:
    """Resolve DEPLOY_DIR_NAME, defaulting to CWD when it is a deployment directory."""
    if deploy_dir_name is not None:
        return Path(deploy_dir_name)
    from .role import detect_role
    role, _ = detect_role()
    if role == "deployer":
        return Path(".")
    raise click.UsageError(
        "DEPLOY_DIR_NAME required: current directory is not a deployment directory."
    )


@click.command("build")
@click.argument("deploy_dir_name", required=False, metavar="DEPLOY_DIR_NAME",
                type=click.Path(exists=True, file_okay=False))
def build(deploy_dir_name: str | None) -> None:
    """Build Docker images for a UI deployment."""
    _run_compose(_deployment_dir(deploy_dir_name), "build")


@click.command("up")
@click.argument("deploy_dir_name", required=False, metavar="DEPLOY_DIR_NAME",
                type=click.Path(exists=True, file_okay=False))
def up(deploy_dir_name: str | None) -> None:
    """Start a UI deployment in detached mode."""
    from . import containers as _containers
    deploy_dir = _deployment_dir(deploy_dir_name)
    deploy_name = deploy_dir.resolve().name.lower()
    container_names = [f"jejune-{deploy_name}-{svc}-1" for svc in _UI_SERVICES]
    _containers.unregister(*container_names)
    for cname in container_names:
        _containers.register(deploy_name, cname)
    _run_compose(deploy_dir, "--project-name", f"jejune-{deploy_name}", "up", "-d")


@click.command("down")
@click.argument("deploy_dir_name", required=False, metavar="DEPLOY_DIR_NAME",
                type=click.Path(exists=True, file_okay=False))
def down(deploy_dir_name: str | None) -> None:
    """Stop a UI deployment."""
    _run_compose(_deployment_dir(deploy_dir_name), "down")
