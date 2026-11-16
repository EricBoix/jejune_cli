"""converters click group — catalog-aware multi-repo converter commands."""

import sys

import click

from jejune_cli.core._package_paths import CatalogConfig
from jejune_cli.core.app_context import AppContext


@click.group(short_help="Catalog converter image operations")
def converters():
    """Build and test converter images for all catalog documents."""


@click.command("build")
@click.argument("build_name", required=False, default=None, metavar="[BUILD_NAME]")
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
    "--local-documents",
    is_flag=True,
    default=False,
    help="Copy the local jejune_doc_* clones into the images (instead of git cloning them).",
)
@click.option(
    "--local-pdf-to-markdown",
    is_flag=True,
    default=False,
    help="Use the local pdf-to-markdown (instead of the uv.lock version).",
)
@click.option(
    "--local",
    is_flag=True,
    default=False,
    help="Same as --local-documents --local-pdf-to-markdown.",
)
def converters_build(
    build_name,
    catalog_file,
    root_dir,
    repo,
    no_cache,
    local_documents,
    local_pdf_to_markdown,
    local,
):
    """Build converter images for all catalog documents.

    An optional BUILD_NAME restricts the run to a single repository (by name).

    By default an image clones its document from GitHub and uses the pdf-to-markdown
    version locked in the uv.lock of the document. The --local-* flags use instead
    the local clones, searched in $JEJUNE_ROOT_DIR (or --root-dir), then in
    .jejune/tmp (pdf-to-markdown is cloned there when found nowhere). The sources
    used are recorded as image labels, which `converters test` reports.
    """
    app = click.get_current_context().find_object(AppContext)
    converters_comp = app.component_registry.get("converters")
    converters_comp.build(
        no_cache,
        catalog_file,
        build_name or repo,
        root_dir,
        local_documents or local,
        local_pdf_to_markdown or local,
    )


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
    "--local-documents",
    is_flag=True,
    default=False,
    help="Test the images built with the local jejune_doc_* clones.",
)
@click.option(
    "--local-pdf-to-markdown",
    is_flag=True,
    default=False,
    help="Test the images built with the local pdf-to-markdown.",
)
@click.option(
    "--local",
    is_flag=True,
    default=False,
    help="Same as --local-documents --local-pdf-to-markdown.",
)
@click.option("--verbose", is_flag=True, default=False, help="Show full docker output.")
def converters_test(
    test_name,
    catalog_file,
    root_dir,
    repo,
    no_cache,
    local_documents,
    local_pdf_to_markdown,
    local,
    verbose,
):
    """Build (when needed) and test converter containers for all catalog documents.

    An optional TEST_NAME restricts the run to a single repository (by name).

    For each document that has a DockerContext/, tests the converter image built
    with the selected sources (default ones, or the --local-* ones): the image is
    first built, as `converters build` does with the same flags, when it does
    not exist yet (or with --no-cache). Then runs `docker run --test` (pytest
    vs. reference).

    \b
    unchanged       — tests pass (conversion matches reference)
    changed         — tests fail (conversion drift detected)
    build-failed    — image did not build
    image-not-found — image still absent after its build
    skipped         — no DockerContext in this repo
    """
    local_documents = local_documents or local
    local_pdf_to_markdown = local_pdf_to_markdown or local
    app = click.get_current_context().find_object(AppContext)
    collection = app.component_registry.get("catalog").collection
    converters_comp = app.component_registry.get("converters")
    selection = collection.select(catalog_file, test_name or repo, root_dir)

    counts = {
        "unchanged": 0,
        "changed": 0,
        "build_failed": 0,
        "image_not_found": 0,
        "skipped": 0,
    }
    _COLORS = {
        "unchanged": "green",
        "changed": "red",
        "build_failed": "red",
        "image_not_found": "red",
        "skipped": "yellow",
    }
    col = 42

    for name, _url, repo_dir in collection.iter_documents(
        selection.documents, selection.directories
    ):
        outcome, detail, verbose_output = converters_comp.run_converter_test(
            repo_dir,
            name,
            catalog_file,
            root_dir,
            no_cache,
            local_documents,
            local_pdf_to_markdown,
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
        f"{counts['image_not_found']} image-not-found  "
        f"{counts['skipped']} skipped"
    )
    if counts["changed"] or counts["build_failed"] or counts["image_not_found"]:
        sys.exit(1)


converters.add_command(converters_build, "build")
converters.add_command(converters_test, "test")
