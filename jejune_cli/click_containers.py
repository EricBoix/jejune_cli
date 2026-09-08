"""Click commands for managing jejune-managed Docker containers."""
import click

from .component_containerized import cont_comp


def _print_containers_table(prefix: str = "  ") -> None:
    from .component_registry import REGISTRY as COMP_REGISTRY

    comps = [inst for inst in COMP_REGISTRY if isinstance(inst, cont_comp)]
    if not comps:
        click.echo(f"{prefix}No container components registered.")
        return

    _W_COMP = max(len(inst.name) for inst in comps)
    _W_IMG = max(len(inst.image_name) for inst in comps)
    header = f"{prefix}{'Component':<{_W_COMP}}  {'Image':<{_W_IMG}}  Status"
    click.echo(header)
    click.echo(prefix + "─" * (len(header) - len(prefix)))
    for inst in comps:
        ok, msg = inst.is_running()
        status_str = click.style("running", fg="green") if ok else click.style(msg, fg="yellow")
        click.echo(f"{prefix}{inst.name:<{_W_COMP}}  {inst.image_name:<{_W_IMG}}  {status_str}")


@click.group("containers", short_help="Manage jejune-managed Docker containers")
def containers_cli():
    """Manage Docker containers orchestrated by jejune."""


@containers_cli.command("list")
def containers_list():
    """List all Docker containers managed by jejune with their status."""
    entries = cont_comp.existing_component_containers()
    if not entries:
        click.echo("No containers on record.")
        return
    _print_containers_table(prefix="")


@containers_cli.command("exit")
def containers_exit():
    """Stop all detached containers launched by jejune."""
    entries = cont_comp.existing_component_containers()
    if not entries:
        click.echo("No containers on record.")
        return
    for entry in entries:
        name = entry["container"]
        click.echo(f"Stopping {name} ...")
        cont_comp._docker.stop_container(name)
    cont_comp.unregister_containers(*(e["container"] for e in entries))
    click.echo(click.style("All containers stopped.", fg="green"))
