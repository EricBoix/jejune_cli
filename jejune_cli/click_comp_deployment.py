"""Deployment CLI group and commands."""

import os
import sys
from pathlib import Path

import click

from .app_context import AppContext


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
    click.echo("Installing catalog repositories...")
    n = app.component_registry.get("catalog").install_catalog()
    click.echo(f"{n} repo(s) ready.")
    click.echo("Installing deployer plugin packages...")
    app.component_registry.get("plugin-packages").install_packages()


for _cmd in (status, build, up, down, deployment_install):
    deployment.add_command(_cmd)
