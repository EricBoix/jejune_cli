"""UI deployment commands — attached to the `deployment` group by deployment.py."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
import yaml

from ._env import load_deployment_env
from .deployer_extensions import (
    _DEPLOYER_CHECK_PACKAGES,
    _extensions_installed,
)
from .ecosystem import check_docker, check_uv
from .next_steps import HeuristicStep, print_next_steps, register_heuristic, register_precondition, register_role_ordering

_TEMPLATES = Path(__file__).parent / "templates"
_T_UI = _TEMPLATES / "deployer" / "ui-deployment"


def _trivial_catalog_content() -> str | None:
    """Return the trivial catalog template content from the installed catalog plugin."""
    try:
        from importlib.resources import files
        return (files("jejune_catalog_check") / "templates" / "trivial-catalog.yaml").read_text()
    except Exception:
        return None

_UI_SERVICES = ("docs-server", "kg-graph-viewer", "markdown-browser")


# ---------------------------------------------------------------------------
# Heuristic conditions for `jejune next`
# ---------------------------------------------------------------------------

def _is_deployer_cwd() -> bool:
    from .role import detect_role
    role, _ = detect_role()
    return role == "deployer"


def _deploy_catalog_needs_configuration() -> bool:
    """True when catalog.yaml is still the unedited trivial template."""
    catalog = Path(".") / "catalog.yaml"
    if not catalog.exists():
        return False
    template = _trivial_catalog_content()
    if template is None:
        return False
    return catalog.read_text() == template


def _deploy_env_is_default() -> bool:
    """True when deployment.env still matches the scaffold template."""
    env_file = Path(".") / "deployment.env"
    template = _T_UI / "deployment.env"
    if not env_file.exists() or not template.exists():
        return False
    return env_file.read_text() == template.read_text()


def _deploy_config_is_default() -> bool:
    """True when catalog.yaml or deployment.env is still at template defaults."""
    return _deploy_catalog_needs_configuration() or _deploy_env_is_default()


def _deploy_images_missing() -> bool:
    name = Path(".").resolve().name  # preserve case — matches {{NAME}} in docker-compose.yml image tags
    for svc in _UI_SERVICES:
        r = subprocess.run(
            ["docker", "image", "inspect", f"jejune:{name}-{svc}"],
            capture_output=True,
        )
        if r.returncode != 0:
            return True
    return False


def _deploy_containers_running() -> bool:
    from . import containers as _c
    name = Path(".").resolve().name.lower()
    return all(_c.is_running(f"jejune-{name}-{svc}-1") for svc in _UI_SERVICES)



def _check_ui_services() -> list[tuple[str, bool, str]]:
    from .plugin import _REGISTRY
    plugins = {p.name: p for p in _REGISTRY}
    results = []
    for _, _, name in _DEPLOYER_CHECK_PACKAGES:
        p = plugins.get(name)
        ok, msg = p.check_availability() if (p and p.check_availability) else (False, "not installed")
        results.append((name, ok, msg))
    return results


def _deploy_services_available() -> bool:
    return _extensions_installed() and all(ok for _, ok, _ in _check_ui_services())


register_precondition("deployer role detected",        _is_deployer_cwd)
register_precondition("deployment config is default",  _deploy_config_is_default)
register_precondition("deployment images missing",     _deploy_images_missing)
register_precondition("deployment containers running", _deploy_containers_running)
register_precondition("deployment services available", _deploy_services_available)


def _docs_server_url() -> str:
    port = "8765"
    env_file = Path(".") / "deployment.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DOCS_SERVER_PORT="):
                port = line.split("=", 1)[1].strip()
                break
    return f"http://localhost:{port}"


register_heuristic(HeuristicStep(
    label="Install docker desktop",
    command=None, order=2,
    conditions=[_is_deployer_cwd],
    anti_conditions=[check_docker],
), roles={"deployer"})

register_heuristic(HeuristicStep(
    label="Wrap up configuration",
    command="edit config files", order=5,
    conditions=[_is_deployer_cwd, _deploy_config_is_default],
    anti_conditions=[],
), roles={"deployer"})

register_heuristic(HeuristicStep(
    label="Build deployment", command="jejune build", order=10,
    conditions=[_is_deployer_cwd, check_docker, _deploy_images_missing],
    anti_conditions=[],
), roles={"deployer"})

register_heuristic(HeuristicStep(
    label="Start deployment", command="jejune up", order=20,
    conditions=[_is_deployer_cwd, check_docker],
    anti_conditions=[_deploy_images_missing, _deploy_containers_running],
), roles={"deployer"})

register_heuristic(HeuristicStep(
    label="Install deployer CLI extensions",
    command="jejune deployment extensions install", order=22,
    conditions=[_is_deployer_cwd, check_uv, _deploy_containers_running],
    anti_conditions=[_extensions_installed],
), roles={"deployer"})

register_heuristic(HeuristicStep(
    label="Check deployment status", command="jejune deployment status", order=25,
    conditions=[_is_deployer_cwd, check_uv, _deploy_containers_running, _extensions_installed],
    anti_conditions=[_deploy_services_available],
), roles={"deployer"})

register_heuristic(HeuristicStep(
    label="Browse docs server",
    command=lambda: f"web-browse UI at {_docs_server_url()}", order=30,
    conditions=[_is_deployer_cwd, _deploy_containers_running, _deploy_services_available],
    anti_conditions=[],
), roles={"deployer"})

register_heuristic(HeuristicStep(
    label="Deployment running stop", command="jejune down", order=35,
    conditions=[_is_deployer_cwd, check_docker, _deploy_containers_running],
    anti_conditions=[],
), roles={"deployer"})

register_role_ordering("deployer", {
    "Wrap up configuration": -1,
})


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


def _compose_returncode(deploy_dir: Path, *args: str) -> int:
    from .ecosystem import DEPLOYER_REPOS, resolve, resolve_dirs

    env = os.environ.copy()
    root_dir, tmp_dir = resolve_dirs(deploy_dir)
    if root_dir:
        env["JEJUNE_ROOT_DIR"] = str(root_dir)

    for name, subpath, key in DEPLOYER_REPOS:
        if key:
            env[key] = resolve(name, root_dir, tmp_dir, subpath)

    result = subprocess.run(
        ["docker", "compose", "--env-file", "deployment.env", *args],
        cwd=deploy_dir,
        env=env,
    )
    return result.returncode


def _run_compose(deploy_dir: Path, *args: str) -> None:
    sys.exit(_compose_returncode(deploy_dir, *args))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@click.command("status")
@click.argument("deploy_dir_name", required=False, metavar="DEPLOY_DIR_NAME",
                type=click.Path(exists=True, file_okay=False))
def status(deploy_dir_name: str | None) -> None:
    """Show HTTP availability of the three UI deployment services."""
    deploy_dir = _deployment_dir(deploy_dir_name)
    load_deployment_env(deploy_dir)
    if not _extensions_installed():
        click.echo(click.style("Check extensions not installed.", fg="red"), err=True)
        click.echo("Run: jejune deployment extensions install", err=True)
        raise SystemExit(1)
    results = _check_ui_services()
    from .plugin import _REGISTRY
    plugin_port = {
        p.name: os.environ.get(p.config_vars[0], "?")
        for p in _REGISTRY if p.config_vars
    }
    _W = max(len(n) for n, *_ in results)
    for name, ok, msg in results:
        label = click.style("ok", fg="green") if ok else click.style("error", fg="red")
        if not ok:
            msg = f"{msg} on port {plugin_port.get(name, '?')}"
        click.echo(f"  {name:<{_W}}  {label}  {msg}")


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
    shutil.copy(_T_UI / "env-config", dot_jejune / "env-config")

    full_catalog = _full_catalog_path(deployments_dir)
    if full_catalog:
        shutil.copy(full_catalog, deploy_dir / "catalog.yaml")
        click.echo(f"Seeded catalog.yaml from {full_catalog}")
    else:
        template = _trivial_catalog_content()
        if template:
            (deploy_dir / "catalog.yaml").write_text(template)
        else:
            (deploy_dir / "catalog.yaml").write_text("documents: []\n")
        click.echo("Seeded catalog.yaml from built-in template — populate manually.")

    has_private = _has_private_repos(deploy_dir / "catalog.yaml")
    (deploy_dir / "docker-compose.yml").write_text(_docker_compose_content(has_private, name))
    shutil.copy(_T_UI / "deployment.env", deploy_dir / "deployment.env")

    if has_private:
        (deploy_dir / ".gitignore").write_text("secrets.env\n")
        shutil.copy(_T_UI / "secrets.env.template", deploy_dir / "secrets.env.template")

    click.echo(f"Created {deploy_dir}")
    print_next_steps(cwd=deploy_dir)


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
    """Resolve DEPLOY_DIR_NAME, defaulting to CWD when omitted."""
    return Path(deploy_dir_name) if deploy_dir_name is not None else Path(".")


@click.command("build")
@click.argument("deploy_dir_name", required=False, metavar="DEPLOY_DIR_NAME",
                type=click.Path(exists=True, file_okay=False))
@click.option("--no-cache", is_flag=True, default=False,
              help="Do not use cache when building images.")
def build(deploy_dir_name: str | None, no_cache: bool) -> None:
    """Build Docker images for a UI deployment."""
    if no_cache:
        # --no-cache on `docker compose build` only skips the image-layer cache.
        # BuildKit keeps a separate source cache for git context fetches; prune it
        # first so that "load git source" steps are also re-executed from scratch.
        subprocess.run(["docker", "builder", "prune", "--force"], check=True)
    extra = ["--no-cache"] if no_cache else []
    _run_compose(_deployment_dir(deploy_dir_name), "build", *extra)


@click.command("up")
@click.argument("deploy_dir_name", required=False, metavar="DEPLOY_DIR_NAME",
                type=click.Path(exists=True, file_okay=False))
def up(deploy_dir_name: str | None) -> None:
    """Start a UI deployment in detached mode."""
    from . import containers as _containers
    from .deployer_extensions import _do_extensions_install
    deploy_dir = _deployment_dir(deploy_dir_name)
    deploy_name = deploy_dir.resolve().name.lower()
    container_names = [f"jejune-{deploy_name}-{svc}-1" for svc in _UI_SERVICES]
    _containers.unregister(*container_names)
    for cname in container_names:
        _containers.register(deploy_name, cname)
    rc = _compose_returncode(deploy_dir, "--project-name", f"jejune-{deploy_name}", "up", "-d")
    if rc == 0 and not _extensions_installed():
        click.echo("\nInstalling deployer CLI extensions...")
        _do_extensions_install()
    sys.exit(rc)


@click.command("down")
@click.argument("deploy_dir_name", required=False, metavar="DEPLOY_DIR_NAME",
                type=click.Path(exists=True, file_okay=False))
def down(deploy_dir_name: str | None) -> None:
    """Stop a UI deployment."""
    _run_compose(_deployment_dir(deploy_dir_name), "down")
