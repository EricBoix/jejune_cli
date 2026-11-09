"""converters click group — catalog-aware multi-repo converter commands."""

import sys

import click

from ._package_paths import CatalogConfig
from .app_context import AppContext


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
    envvar=CatalogConfig.ROOT_DIR_ENV_VAR,
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
def converters_test(
    test_name, catalog_file, root_dir, repo, no_cache, no_build, verbose
):
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
    app = click.get_current_context().find_object(AppContext)
    collection = app.component_registry.get("catalog").collection
    converters_comp = app.component_registry.get("converters")
    selection = collection.select(catalog_file, test_name or repo, root_dir)

    counts = {"unchanged": 0, "changed": 0, "build_failed": 0, "skipped": 0}
    _COLORS = {
        "unchanged": "green",
        "changed": "red",
        "build_failed": "red",
        "skipped": "yellow",
    }
    col = 42

    for name, _url, repo_dir in collection.iter_documents(
        selection.documents, selection.directories
    ):
        outcome, detail, verbose_output = converters_comp.run_converter_test(
            repo_dir, no_cache, no_build
        )
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
