"""converters click group — catalog-aware multi-repo converter commands.

The options of its commands carry the names and the meaning of the ones of the
`convert` commands (single document): `converters` loops over the documents of a
catalog.
"""

import sys
from pathlib import Path

import click

from jejune_cli.core._package_paths import CatalogConfig
from jejune_cli.core.app_context import AppContext


class ConvertersOptions:
    """The click options shared by the commands of the converters group."""

    @staticmethod
    def catalog_selection(command):
        for option in reversed(
            (
                click.argument(
                    "document_name", required=False, default=None, metavar="[NAME]"
                ),
                click.option(
                    "--catalog",
                    "catalog_file",
                    default=None,
                    type=click.Path(),
                    help="Catalog file (default: $JEJUNE_CATALOG or ./catalog.yaml).",
                ),
                click.option(
                    "--root-dir",
                    envvar=CatalogConfig.ROOT_DIR_ENV_VAR,
                    default=None,
                    type=click.Path(),
                    help="Directory holding jejune_doc_* clones (default: $JEJUNE_ROOT_DIR).",
                ),
                click.option(
                    "--repo", default=None, help="Restrict to one repository (by name)."
                ),
            )
        ):
            command = option(command)
        return command

    @staticmethod
    def sources(command):
        for option in reversed(
            (
                click.option(
                    "--no-cache",
                    is_flag=True,
                    default=False,
                    help="Bypass Docker layer cache.",
                ),
                click.option(
                    "--no-local-document",
                    is_flag=True,
                    default=False,
                    help="Use the images with the documents cloned from GitHub (instead "
                    "of copying the local jejune_doc_* clones).",
                ),
                click.option(
                    "--local-pdf-to-markdown",
                    is_flag=True,
                    default=False,
                    help="Use the images with the local pdf-to-markdown (instead of "
                    "the uv.lock version).",
                ),
            )
        ):
            command = option(command)
        return command


@click.group(short_help="Catalog converter image operations")
def converters():
    """Build, run and test converter images for all catalog documents."""


@click.command("build")
@ConvertersOptions.catalog_selection
@ConvertersOptions.sources
def converters_build(
    document_name,
    catalog_file,
    root_dir,
    repo,
    no_cache,
    no_local_document,
    local_pdf_to_markdown,
):
    """Build converter images for all catalog documents.

    An optional NAME restricts the run to a single repository (by name).

    By default an image copies its document from the local clone (the uncommitted
    changes included) and uses the pdf-to-markdown version locked in the uv.lock of
    the document. --no-local-document clones the document from GitHub instead;
    --local-pdf-to-markdown uses the local pdf-to-markdown. Local clones are searched
    in $JEJUNE_ROOT_DIR (or --root-dir), then in .jejune/tmp (a document or
    pdf-to-markdown is cloned there when found nowhere). The sources used are
    recorded as image labels, which `converters test` reports.
    """
    app = click.get_current_context().find_object(AppContext)
    converters_comp = app.component_registry.get("converters")
    converters_comp.build(
        no_cache,
        catalog_file,
        document_name or repo,
        root_dir,
        not no_local_document,
        local_pdf_to_markdown,
    )


@click.command("test")
@ConvertersOptions.catalog_selection
@ConvertersOptions.sources
@click.option("--verbose", is_flag=True, default=False, help="Show full docker output.")
def converters_test(
    document_name,
    catalog_file,
    root_dir,
    repo,
    no_cache,
    no_local_document,
    local_pdf_to_markdown,
    verbose,
):
    """Build (when needed) and test converter containers for all catalog documents.

    An optional NAME restricts the run to a single repository (by name).

    For each document that has a DockerContext/, tests the converter image built
    with the selected sources (same options as `converters build`): the image is
    first built, as `converters build` does, when it does not exist yet (or with
    --no-cache). Then runs `docker run --test` (pytest vs. reference).

    \b
    unchanged       — tests pass (conversion matches reference)
    changed         — tests fail (conversion drift detected)
    build-failed    — image did not build
    image-not-found — image still absent after its build
    skipped         — no DockerContext in this repo
    """
    local_documents = not no_local_document
    app = click.get_current_context().find_object(AppContext)
    collection = app.component_registry.get("catalog").collection
    converters_comp = app.component_registry.get("converters")
    selection = collection.select(catalog_file, document_name or repo, root_dir)

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


@click.command(
    "run",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@ConvertersOptions.catalog_selection
@ConvertersOptions.sources
@click.option(
    "--output-dir",
    default="./converted",
    show_default=True,
    help="Host directory receiving the conversion of each document, in a "
    "subdirectory named after the document.",
)
@click.option(
    "--warnings",
    is_flag=True,
    default=False,
    help="Report conversion warnings (e.g. typos that cannot be found).",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Report debug traces of the conversion (implies --warnings).",
)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def converters_run(
    document_name,
    catalog_file,
    root_dir,
    repo,
    no_cache,
    no_local_document,
    local_pdf_to_markdown,
    output_dir,
    warnings,
    debug,
    extra_args,
):
    """Convert all catalog documents, forwarding EXTRA_ARGS to their entrypoint.

    An optional NAME restricts the run to a single repository (by name). Each
    document is converted by its converter image selected as in `converters
    build` (built first when it does not exist yet, or with --no-cache): the
    conversion of the document NAME is written in OUTPUT_DIR/NAME.

    \b
    converted       — conversion done
    failed          — the converter exited with an error
    build-failed    — image did not build
    image-not-found — image still absent after its build
    skipped         — no DockerContext in this repo
    """
    local_documents = not no_local_document
    app = click.get_current_context().find_object(AppContext)
    collection = app.component_registry.get("catalog").collection
    converters_comp = app.component_registry.get("converters")
    selection = collection.select(catalog_file, document_name or repo, root_dir)
    output_root = Path(output_dir).resolve()

    counts = {
        "converted": 0,
        "failed": 0,
        "build_failed": 0,
        "image_not_found": 0,
        "skipped": 0,
    }
    _COLORS = {
        "converted": "green",
        "failed": "red",
        "build_failed": "red",
        "image_not_found": "red",
        "skipped": "yellow",
    }
    col = 42

    for name, _url, repo_dir in collection.iter_documents(
        selection.documents, selection.directories
    ):
        outcome, detail = converters_comp.run_converter_convert(
            repo_dir,
            name,
            catalog_file,
            root_dir,
            no_cache,
            output_root / name,
            local_documents,
            local_pdf_to_markdown,
            warnings,
            debug,
            extra_args,
        )
        counts[outcome] += 1
        label = click.style(outcome.replace("_", "-"), fg=_COLORS[outcome])
        click.echo(f"  {name:<{col}}  {label}  {detail}")

    click.echo()
    click.echo(
        f"  {counts['converted']} converted  "
        f"{counts['failed']} failed  "
        f"{counts['build_failed']} build-failed  "
        f"{counts['image_not_found']} image-not-found  "
        f"{counts['skipped']} skipped"
    )
    if counts["failed"] or counts["build_failed"] or counts["image_not_found"]:
        sys.exit(1)


converters.add_command(converters_build, "build")
converters.add_command(converters_run, "run")
converters.add_command(converters_test, "test")
