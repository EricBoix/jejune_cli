"""converters click group — catalog-aware multi-repo converter commands."""

import sys
from pathlib import Path

import click

from .app_context import AppContext
from .click_catalog_helpers import (
    convert_test_doc,
    iter_docs,
    load_catalog_docs,
)


@click.group(short_help="Catalog converter image operations")
def converters():
    """Build and test converter images for all catalog documents."""


@click.command("test")
@click.argument("test_name", required=False, default=None, metavar="[TEST_NAME]")
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
@click.option("--verbose", is_flag=True, default=False, help="Show full docker output.")
def converters_test(test_name, catalog_file, root_dir, repo, no_cache, no_build, verbose):
    """Build and test converter containers for all catalog documents.

    An optional TEST_NAME restricts the run to a single repository (by name).

    For each document that has a DockerContext/, builds the converter image
    (unless --no-build) then runs `docker run --test` (pytest vs. reference).

    \b
    unchanged    — tests pass (conversion matches reference)
    changed      — tests fail (conversion drift detected)
    build-failed — image did not build
    skipped      — no DockerContext in this repo
    """
    docs = load_catalog_docs(catalog_file)
    filter_name = test_name or repo
    if filter_name:
        docs = [d for d in docs if d["name"] == filter_name]
        if not docs:
            raise click.ClickException(f"Repository '{filter_name}' not found in catalog.")
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
        outcome, detail, verbose_output = convert_test_doc(repo_dir, no_cache, no_build)
        counts[outcome] += 1
        label = click.style(outcome.replace("_", "-"), fg=_COLORS[outcome])
        click.echo(f"  {name:<{col}}  {label}  {detail}")
        if verbose and verbose_output:
            for line in verbose_output.splitlines():
                click.echo(f"    {line}")

    click.echo()
    click.echo(
        f"  {counts['unchanged']} unchanged  "
        f"{counts['changed']} changed  "
        f"{counts['build_failed']} build-failed  "
        f"{counts['skipped']} skipped"
    )
    if counts["changed"] or counts["build_failed"]:
        sys.exit(1)


converters.add_command(converters_test, "test")
