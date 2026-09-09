"""Deployment CLI group and commands."""

import os
import shutil
import sys
from pathlib import Path

import click

from ._env import load_deployment_env
from .component_registry import REGISTRY as COMP_REGISTRY
from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY

_TEMPLATES = Path(__file__).parent / "templates"
_T_UI = _TEMPLATES / "deployer" / "ui-deployment"


@click.group(short_help="Manage deployments")
def deployment():
    """Manage deployments — collections of active jejune_doc_* repositories (collection-level)."""


@click.command("status")
def status() -> None:
    """Show HTTP availability of the three UI deployment services."""
    load_deployment_env(Path("."))
    if not PLUGIN_PACKAGE_CATALOG.packages_installed():
        click.echo(click.style("Check plugin packages not installed.", fg="red"), err=True)
        click.echo("Run: jejune plugin-packages install", err=True)
        raise SystemExit(1)
    results = COMP_REGISTRY.get("deployment").check_ui_services()
    from .plugin_registry import PLUGIN_REGISTRY
    plugin_port = {
        p.name: os.environ.get(p.config_vars[0], "?")
        for p in PLUGIN_REGISTRY.plugins if p.config_vars
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

    catalog_comp = COMP_REGISTRY.get("catalog")
    full_catalog = catalog_comp.full_catalog_path(deployments_dir)
    if full_catalog:
        shutil.copy(full_catalog, deploy_dir / "catalog.yaml")
        click.echo(f"Seeded catalog.yaml from {full_catalog}")
    else:
        template = catalog_comp.trivial_catalog_content()
        if template:
            (deploy_dir / "catalog.yaml").write_text(template)
        else:
            (deploy_dir / "catalog.yaml").write_text("documents: []\n")
        click.echo("Seeded catalog.yaml from built-in template — populate manually.")

    has_private = catalog_comp.has_private_repos(deploy_dir / "catalog.yaml")
    (deploy_dir / "docker-compose.yml").write_text(
        COMP_REGISTRY.get("deployment").generate_docker_compose(has_private, name, _T_UI)
    )
    shutil.copy(_T_UI / "deployment.env", deploy_dir / "deployment.env")

    if has_private:
        (deploy_dir / ".gitignore").write_text("secrets.env\n")
        shutil.copy(_T_UI / "secrets.env.template", deploy_dir / "secrets.env.template")

    click.echo(f"Creating deployment in ./{deploy_dir.name}/ sub-directory")
    HEURISTIC_STEP_REGISTRY.print_next_steps(cwd=deploy_dir)


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


@click.command("build")
@click.option("--no-cache", is_flag=True, default=False,
              help="Do not use cache when building images.")
def build(no_cache: bool) -> None:
    """Build Docker images for a UI deployment."""
    sys.exit(COMP_REGISTRY.get("deployment").build(Path("."), no_cache=no_cache))


@click.command("up")
def up() -> None:
    """Start a UI deployment in detached mode."""
    from .component_containerized import cont_comp
    from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
    deploy_dir = Path(".")
    deploy_name = deploy_dir.resolve().name.lower()
    deployment_comp = COMP_REGISTRY.get("deployment")
    container_names = [f"jejune-{deploy_name}-{svc}-1" for svc in deployment_comp.service_names]
    cont_comp.unregister_containers(*container_names)
    for cname in container_names:
        cont_comp.register_container(deploy_name, cname)
    rc = deployment_comp.run_compose(deploy_dir, "--project-name", f"jejune-{deploy_name}", "up", "-d")
    if rc == 0 and not PLUGIN_PACKAGE_CATALOG.packages_installed():
        click.echo("\nInstalling deployer plugin packages...")
        PLUGIN_PACKAGE_CATALOG.install_packages()
    sys.exit(rc)


@click.command("down")
def down() -> None:
    """Stop a UI deployment."""
    sys.exit(COMP_REGISTRY.get("deployment").run_compose(Path("."), "down"))


@click.command("install")
def deployment_install() -> None:
    """Install all deployment components: catalog repos and plugin packages."""
    from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
    try:
        from jejune_catalog._commands import _do_catalog_install
        click.echo("Installing catalog repositories...")
        _do_catalog_install()
    except ImportError:
        click.echo(click.style(
            "  catalog plugin not installed — skipping", fg="yellow"
        ))
    click.echo("Installing deployer plugin packages...")
    PLUGIN_PACKAGE_CATALOG.install_packages()


for _cmd in (status, ui_list, build, up, down, deployment_install):
    deployment.add_command(_cmd)
