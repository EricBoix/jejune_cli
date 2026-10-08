"""Click command group and all catalog subcommands."""

import shutil
import sys
from importlib import resources
from pathlib import Path

import click

from .app_context import AppContext
from .click_cont_comp_convert import convert
from .click_catalog_helpers import (
    convert_test_doc,
    load_catalog_docs,
    catalog_config_status,
    check_catalog,
    iter_docs,
    sync_catalog,
)
from .component_manifest import CompManifest


def _detect_role():
    return (
        click.get_current_context().find_object(AppContext).role_registry.detect_role()
    )


# Commands accessible to deployer (via deployment-catalog role) AND collection role.
_DEPLOYMENT_CATALOG_ONLY: frozenset[str] = frozenset({"check-deployment"})

# Commands accessible to catalog-contributor only.
_COLLECTION_ONLY: frozenset[str] = frozenset(
    {
        "sync",
        "test",
        "install",
        "sample",
        "status-config",
        "hint-config",
        "status-availability",
        "hint-availability",
    }
)


# ---------------------------------------------------------------------------
# Role-aware group
# ---------------------------------------------------------------------------


class _CatalogGroup(click.Group):
    """Hides and blocks role-gated commands based on the active role."""

    def _is_collection_role(self) -> bool:
        return _detect_role().is_catalog_contributor()

    def _is_deployment_catalog_role(self) -> bool:
        """True for deployer (inherits deployment-catalog) and collection role."""
        active_role = _detect_role()
        registry = click.get_current_context().find_object(AppContext).role_registry
        return (
            registry.role_is_deployment_catalog_family(active_role)
            or active_role.is_catalog_contributor()
        )

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        is_collection = self._is_collection_role()
        is_deployment_catalog = self._is_deployment_catalog_role()
        commands = []
        for name in self.list_commands(ctx):
            if not is_collection and name in _COLLECTION_ONLY:
                continue
            if not is_deployment_catalog and name in _DEPLOYMENT_CATALOG_ONLY:
                continue
            cmd = self.get_command(ctx, name)
            if cmd and not cmd.hidden:
                commands.append((name, cmd))
        if commands:
            with formatter.section("Commands"):
                formatter.write_dl(
                    [
                        (name, cmd.get_short_help_str(limit=formatter.width))
                        for name, cmd in commands
                    ]
                )

    def invoke(self, ctx: click.Context) -> object:
        cmd_name = ctx._protected_args[0] if ctx._protected_args else None
        if cmd_name in _COLLECTION_ONLY and not self._is_collection_role():
            raise click.ClickException(
                f"'{cmd_name}' is only available for the catalog-contributor role."
            )
        if (
            cmd_name in _DEPLOYMENT_CATALOG_ONLY
            and not self._is_deployment_catalog_role()
        ):
            raise click.ClickException(
                f"'{cmd_name}' requires the deployment-catalog role "
                f"(or catalog-contributor)."
            )
        return super().invoke(ctx)


def _print_deployment_results(results: list[tuple[str, bool, str]]) -> bool:
    """Print check-deployment results; return True if all ok."""
    all_ok = True
    for item, ok, msg in results:
        status = click.style(msg, fg="green") if ok else click.style(msg, fg="red")
        if item == "catalog.yaml":
            click.echo(f"  {item:<45} {status}")
        else:
            click.echo(f"    • {item:<41} {status}")
        if not ok:
            all_ok = False
    return all_ok


@click.group("catalog", cls=_CatalogGroup, short_help="Manage the document catalog")
def catalog_group():
    """Manage the catalog of jejune_doc_* repositories."""


# ---------------------------------------------------------------------------
# Doc-level command (available to all catalog roles)
# ---------------------------------------------------------------------------


@catalog_group.command("check")
@click.option(
    "--catalog",
    "catalog_path",
    required=False,
    default=None,
    type=click.Path(),
    help="Collection catalog path. If omitted, validates the current directory's catalog.yaml.",
)
@click.option(
    "--root-dir",
    envvar="JEJUNE_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding jejune_doc_* clones (default: $JEJUNE_ROOT_DIR).",
)
def check(catalog_path, root_dir):
    """Validate a catalog.

    Without --catalog: validates the current directory's catalog.yaml as a
    deployment catalog. With --catalog PATH: verifies a collection catalog
    against GitHub visibility and local clones (catalog-contributor only).
    """
    if catalog_path is None:
        dep_path = Path.cwd()
        if not (dep_path / "catalog.yaml").exists():
            raise click.ClickException(
                "catalog.yaml not found in current directory — "
                "for document manifests use `jejune manifest check-config`"
            )
        app = click.get_current_context().find_object(AppContext)
        catalog_comp = app.component_registry.get("catalog")
        full_cat = catalog_comp.full_catalog_path(dep_path.parent) or Path()
        results = catalog_comp.check_deployment(dep_path, full_cat)
        if not _print_deployment_results(results):
            sys.exit(1)
    else:
        active_role = _detect_role()
        if not active_role.is_catalog_contributor():
            raise click.ClickException(
                "--catalog is only available for the catalog-contributor role."
            )
        cfg_status, hint = catalog_config_status()
        if cfg_status == "error":
            raise click.ClickException(f"not configured — {hint}")
        cat_path = Path(catalog_path)
        root = Path(root_dir) if root_dir else None
        results = check_catalog(cat_path, root)
        if not results:
            click.echo(
                click.style("no documents found in catalog — wrong file?", fg="yellow")
            )
            return
        all_ok = True
        for name, ok, msg in results:
            status = click.style("ok", fg="green") if ok else click.style(msg, fg="red")
            click.echo(f"  {name:<45} {status}")
            if not ok:
                all_ok = False
        if all_ok:
            click.echo(click.style(f"{len(results)} document(s) — all ok.", fg="green"))
        else:
            sys.exit(1)


# ---------------------------------------------------------------------------
# Collection-level commands (catalog-contributor only)
# ---------------------------------------------------------------------------


@catalog_group.command("test")
@click.argument("catalog_file", required=False, default=None)
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
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print referenced files for each document.",
)
def catalog_test(catalog_file, root_dir, repo, verbose):
    """Validate jejune_doc_* repositories found in the catalog.

    CATALOG_FILE defaults to $JEJUNE_CATALOG, then catalog.yaml in the CWD.

    Repositories are expected under ROOT_DIR/<name>/. Missing repositories
    (or all when ROOT_DIR is unset) are cloned into .jejune/tmp/ which is
    gitignored automatically.

    For each repository, manifest.yaml is parsed and every file it references is
    checked for existence. Exits with a non-zero status if any check fails.
    """
    docs = load_catalog_docs(catalog_file)
    app = click.get_current_context().find_object(AppContext)
    ecosystem = app.component_registry.get("ecosystem")
    eco_root, eco_tmp = ecosystem.resolve_dirs()
    root = Path(root_dir) if root_dir and Path(root_dir).is_dir() else eco_root

    if repo:
        docs = [d for d in docs if d["name"] == repo]
        if not docs:
            raise click.ClickException(f"Repository '{repo}' not found in catalog.")

    all_ok = True

    for name, _url, repo_dir in iter_docs(docs, root, eco_tmp, ecosystem):
        cloned_label = click.style("cloned", fg="green")
        errors, file_refs = CompManifest(repo_dir).check_manifest_referenced_files()
        if errors:
            all_ok = False
            doc_label = click.style("invalid", fg="red")
            click.echo(f"  {name:<40}  {cloned_label} / {doc_label}")
            if verbose:
                for err in errors:
                    click.echo(f"      {click.style(err, fg='red')}")
        else:
            doc_label = click.style("valid", fg="green")
            click.echo(f"  {name:<40}  {cloned_label} / {doc_label}")
            if verbose:
                key_width = max((len(k) for k, _ in file_refs), default=0)
                for key, rel in file_refs:
                    click.echo(f"      {key:<{key_width}}  {rel}")

    click.echo()
    if all_ok:
        click.echo(click.style(f"{len(docs)} repo(s) — all ok.", fg="green"))
    else:
        click.echo(click.style(f"{len(docs)} repo(s) — some checks failed.", fg="red"))
        sys.exit(1)


@catalog_group.command("install")
@click.argument("catalog_file", required=False, default=None)
@click.option(
    "--root-dir",
    envvar="JEJUNE_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding side-by-side clones (default: $JEJUNE_ROOT_DIR).",
)
@click.option("--repo", default=None, help="Restrict to one repository (by name).")
def catalog_install(catalog_file, root_dir, repo):
    """Clone missing catalog repositories into .jejune/tmp/."""
    app = click.get_current_context().find_object(AppContext)
    n = app.component_registry.get("catalog").install_catalog(
        catalog_file, root_dir, repo
    )
    click.echo(f"{n} repo(s) ready.")


@catalog_group.command("sample")
def catalog_sample():
    """Copy the built-in catalog template to catalog.yaml in the current directory."""
    target = Path.cwd() / "catalog.yaml"
    if target.exists():
        click.echo(
            click.style(
                f"Warning: {target} already exists — not overwriting.",
                fg="yellow",
            ),
            err=True,
        )
        return
    pkg = (
        resources.files("jejune_cli") / "templates" / "catalog" / "trivial-catalog.yaml"
    )
    shutil.copy(str(pkg), target)
    click.echo(f"Created {target}")


@catalog_group.command("status-config")
def status_config():
    """Show catalog configuration status (mirrors the doctor Config Status column)."""
    status, msg = catalog_config_status()
    if status == "ok":
        click.echo(f"catalog: {click.style('ok', fg='green')}")
    elif status == "warn":
        click.echo(f"catalog: {click.style(msg, fg='yellow')}")
    else:
        click.echo(f"catalog: {click.style('error', fg='red')}")


@catalog_group.command("hint-config")
def hint_config():
    """Show how to fix catalog configuration."""
    status, msg = catalog_config_status()
    if status == "ok":
        click.echo(click.style("catalog is configured", fg="green"))
        return
    click.echo("edit .jejune/env-config (set JEJUNE_ROOT_DIR)")


@catalog_group.command("status-availability")
def status_availability():
    """Show catalog availability status (mirrors the doctor Availability Status column)."""
    app = click.get_current_context().find_object(AppContext)
    catalog_comp = app.component_registry.get("catalog")
    ok_str, msg = catalog_comp.check()
    ok = ok_str != "error"
    if ok:
        click.echo(f"catalog: {click.style('ok', fg='green')}")
    else:
        click.echo(f"catalog: {click.style('error', fg='red')}")


@catalog_group.command("hint-availability")
def hint_availability():
    """Show how to fix catalog availability."""
    app = click.get_current_context().find_object(AppContext)
    catalog_comp = app.component_registry.get("catalog")
    ok_str, msg = catalog_comp.check()
    ok = ok_str != "error"
    if ok:
        click.echo(click.style("catalog is available", fg="green"))
    else:
        click.echo("run `gh auth login` to authenticate the GitHub CLI")


@catalog_group.command("sync")
@click.option(
    "--catalog",
    "catalog_path",
    required=True,
    type=click.Path(),
    help="Path to catalog.yaml.",
)
@click.option(
    "--root-dir",
    envvar="JEJUNE_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding jejune_doc_* clones (default: $JEJUNE_ROOT_DIR).",
)
@click.option(
    "--add",
    "do_add",
    is_flag=True,
    default=False,
    help="Append missing public repos to catalog.yaml.",
)
def sync(catalog_path, root_dir, do_add):
    """Report public jejune_doc_* repos under JEJUNE_ROOT_DIR missing from catalog.yaml."""
    if not root_dir:
        raise click.ClickException(
            "JEJUNE_ROOT_DIR is not set. Use --root-dir or set the env var."
        )
    cat_path = Path(catalog_path)
    results, n_added = sync_catalog(cat_path, Path(root_dir), do_add)
    for name, ok, msg in results:
        if ok:
            status = click.style(msg, fg="green")
        else:
            status = click.style(msg, fg="yellow" if "private" in msg else "red")
        click.echo(f"  {name:<45} {status}")
    if n_added:
        click.echo(f"Added {n_added} repo(s) to {cat_path}.")


@catalog_group.command("check-deployment")
@click.argument("deployment_path", type=click.Path(exists=True))
def check_deployment(deployment_path):
    """Validate a deployment directory against full-catalog.yaml.

    DEPLOYMENT_PATH is the path to a jejune_deployments/deploy_*/ directory.
    The reference catalog is resolved from the sibling jejune_catalog/ repo.
    """
    dep_path = Path(deployment_path)
    app = click.get_current_context().find_object(AppContext)
    catalog_comp = app.component_registry.get("catalog")
    full_cat = catalog_comp.full_catalog_path(dep_path.parent) or Path()
    results = catalog_comp.check_deployment(dep_path, full_cat)
    if not _print_deployment_results(results):
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Standalone command added to convert group by main.py
# ---------------------------------------------------------------------------


@click.command("test")
@click.option(
    "--catalog",
    "catalog_file",
    default=None,
    type=click.Path(),
    help="Catalog file (default: $JEJUNE_CATALOG or ./catalog.yaml).",
)
@click.option(
    "--root-dir",
    envvar="JEJUNE_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding jejune_doc_* clones (default: $JEJUNE_ROOT_DIR).",
)
@click.option("--repo", default=None, help="Restrict to one repository (by name).")
@click.option(
    "--no-cache", is_flag=True, default=False, help="Bypass Docker layer cache."
)
@click.option(
    "--no-build", is_flag=True, default=False, help="Skip build; use cached image."
)
def convert_test(catalog_file, root_dir, repo, no_cache, no_build):
    """Build and test converter containers for all catalog documents.

    For each document that has a DockerContext/, builds the converter image
    (unless --no-build) then runs `docker run --test` (pytest vs. reference).

    \b
    unchanged    — tests pass (conversion matches reference)
    changed      — tests fail (conversion drift detected)
    build-failed — image did not build
    skipped      — no DockerContext in this repo
    """
    docs = load_catalog_docs(catalog_file)
    if repo:
        docs = [d for d in docs if d["name"] == repo]
        if not docs:
            raise click.ClickException(f"Repository '{repo}' not found in catalog.")
    app = click.get_current_context().find_object(AppContext)
    ecosystem = app.component_registry.get("ecosystem")
    eco_root, eco_tmp = ecosystem.resolve_dirs()
    root = Path(root_dir) if root_dir and Path(root_dir).is_dir() else eco_root

    counts = {"unchanged": 0, "changed": 0, "build_failed": 0, "skipped": 0}
    _COLORS = {
        "unchanged": "green",
        "changed": "red",
        "build_failed": "red",
        "skipped": "yellow",
    }
    col = 42

    for name, _url, repo_dir in iter_docs(docs, root, eco_tmp, ecosystem):
        outcome, detail = convert_test_doc(repo_dir, no_cache, no_build)
        counts[outcome] += 1
        label = click.style(outcome.replace("_", "-"), fg=_COLORS[outcome])
        click.echo(f"  {name:<{col}}  {label}  {detail}")

    click.echo()
    click.echo(
        f"  {counts['unchanged']} unchanged  "
        f"{counts['changed']} changed  "
        f"{counts['build_failed']} build-failed  "
        f"{counts['skipped']} skipped"
    )
    if counts["changed"] or counts["build_failed"]:
        sys.exit(1)


convert.add_command(convert_test, "test")
