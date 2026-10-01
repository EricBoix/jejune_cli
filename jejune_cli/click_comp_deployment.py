"""Deployment CLI group and commands."""

import os
import shutil
import sys
from pathlib import Path

import click

from .app_context import AppContext

_TEMPLATES = Path(__file__).parent / "templates"
_T_UI = _TEMPLATES / "deployer" / "ui-deployment"


@click.group(short_help="Manage deployments")
def deployment():
    """Manage deployments — collections of active jejune_doc_* repositories (collection-level)."""


@click.command("status")
@click.pass_context
def status(ctx) -> None:
    """Show HTTP availability of the three UI deployment services."""
    app = ctx.find_object(AppContext)
    plugin_packages_comp = app.component_registry.get("plugin-packages")
    if not plugin_packages_comp.packages_installed():
        click.echo(
            click.style("Check plugin packages not installed.", fg="red"), err=True
        )
        click.echo("Run: jejune plugin-packages install", err=True)
        raise SystemExit(1)
    results = app.component_registry.get("deployment").check_ui_services()
    plugin_port = {
        p.name: os.environ.get(p.config_vars[0], "?")
        for p in app.plugin_registry.plugins
        if p.config_vars
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
@click.pass_context
def ui_configure(ctx, deployments_dir, name):
    """Scaffold a new UI deployment directory NAME in DEPLOYMENTS_DIR.

    Creates catalog.yaml (seeded from the sibling jejune_docs_server repo's
    full-catalog.yaml when available), docker-compose.yml, and deployment.env.
    A .gitignore and secrets.env.template are added only when the catalog
    contains private repositories.
    """
    app = ctx.find_object(AppContext)
    deployments_dir = Path(deployments_dir)
    deploy_dir = deployments_dir / name

    if deploy_dir.exists():
        click.echo(f"Error: {deploy_dir} already exists.", err=True)
        sys.exit(1)

    try:
        deploy_dir.mkdir(parents=True)
    except OSError as exc:
        raise click.ClickException(str(exc)) from exc
    jejune_dir = deploy_dir / ".jejune"
    jejune_dir.mkdir()
    (jejune_dir / "origin").write_text(f"{deploy_dir}\n")
    shutil.copy(_T_UI / "env-config", jejune_dir / "env-config")

    catalog_comp = app.component_registry.get("catalog")
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

    deployment_comp = app.component_registry.get("deployment")
    (deploy_dir / "docker-compose.yml").write_text(
        deployment_comp.generate_docker_compose(deploy_dir, _T_UI)
    )
    shutil.copy(_T_UI / "deployment.env", deploy_dir / "deployment.env")

    if deployment_comp.has_private_repos(deploy_dir):
        (deploy_dir / ".gitignore").write_text("secrets.env\n")
        shutil.copy(_T_UI / "secrets.env.template", deploy_dir / "secrets.env.template")

    click.echo(f"Creating deployment in ./{deploy_dir.name}/ sub-directory")
    app.heuristic_step_registry.print_next_steps(cwd=deploy_dir)


@click.command("list")
@click.argument("deployments_dir", type=click.Path(exists=True))
def ui_list(deployments_dir):
    """List deployments (directories with docker-compose.yml) in DEPLOYMENTS_DIR."""
    root = Path(deployments_dir)
    dirs = sorted(
        d
        for d in root.iterdir()
        if d.is_dir()
        and not d.name.startswith("deploy_")
        and (d / "docker-compose.yml").exists()
    )
    if not dirs:
        click.echo("No UI deployments found.")
        return
    for d in dirs:
        has_catalog = (d / "catalog.yaml").exists()
        status_label = "ok" if has_catalog else "missing catalog.yaml"
        click.echo(f"  {d.name}  [{status_label}]")


@click.command("build")
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Do not use cache when building images.",
)
@click.pass_context
def build(ctx, no_cache: bool) -> None:
    """Build Docker images for a UI deployment."""
    app = ctx.find_object(AppContext)
    sys.exit(
        app.component_registry.get("deployment").build(Path("."), no_cache=no_cache)
    )


@click.command("up")
@click.pass_context
def up(ctx) -> None:
    """Start a UI deployment in detached mode."""
    app = ctx.find_object(AppContext)
    deploy_dir = Path(".")
    deploy_name = deploy_dir.resolve().name.lower()
    deployment_comp = app.component_registry.get("deployment")
    busy = deployment_comp.occupied_host_ports(deploy_dir)
    if busy:
        for port, var in busy:
            click.echo(
                click.style(f"Port {port} ({var}) is already in use.", fg="red"),
                err=True,
            )
        raise SystemExit(1)
    container_names = [
        f"jejune-{deploy_name}-{svc}-1" for svc in deployment_comp.service_names
    ]
    app.coordination.unregister(*container_names)
    for cname in container_names:
        app.coordination.register(deploy_name, cname)
    rc = deployment_comp.run_compose(
        deploy_dir, "--project-name", f"jejune-{deploy_name}", "up", "-d"
    )
    plugin_packages_comp = app.component_registry.get("plugin-packages")
    if rc == 0 and not plugin_packages_comp.packages_installed():
        click.echo("\nInstalling deployer plugin packages...")
        plugin_packages_comp.install_packages()
    sys.exit(rc)


@click.command("down")
@click.pass_context
def down(ctx) -> None:
    """Stop a UI deployment."""
    app = ctx.find_object(AppContext)
    sys.exit(app.component_registry.get("deployment").run_compose(Path("."), "down"))


@click.command("install")
@click.pass_context
def deployment_install(ctx) -> None:
    """Install all deployment components: catalog repos and plugin packages."""
    app = ctx.find_object(AppContext)
    try:
        from jejune_catalog._commands import _do_catalog_install

        click.echo("Installing catalog repositories...")
        _do_catalog_install()
    except ImportError:
        click.echo(
            click.style("  catalog plugin not installed — skipping", fg="yellow")
        )
    click.echo("Installing deployer plugin packages...")
    app.component_registry.get("plugin-packages").install_packages()


for _cmd in (status, ui_list, build, up, down, deployment_install):
    deployment.add_command(_cmd)
