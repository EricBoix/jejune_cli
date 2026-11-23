"""The `jejune images` command group."""

from pathlib import Path

import click

from jejune_cli.click.click_status_table import StatusTable
from jejune_cli.click.click_theme import ClickTheme
from jejune_cli.components.catalog.component_catalog_file import CatalogFile
from jejune_cli.components.containers.converter_commits import ImageAlignment
from jejune_cli.components.containers.image_listing import (
    CommitCell,
    ConvertImageRow,
    ImageListing,
    OtherImageRow,
)
from jejune_cli.core.app_context import AppContext
from jejune_cli.core.component_containerized import ContComp


class _ImagesTable(StatusTable):
    """What the tables of `images list` share: the headers and the cells of the
    verdicts about an image."""

    NAME_HEADER = "Image Name"
    DOCUMENT_HEADER = "Document"
    PDF_TO_MARKDOWN_HEADER = "pdf-to-markdown"
    REPOSITORY_HEADER = "Repository"
    CONVERT_TITLE = "Convert images"
    OTHER_TITLE = "Other images"
    # The `ClickTheme.status_icons` entry of each alignment of an image
    ALIGNMENT_ICON = {
        ImageAlignment.ALIGNED: "ok",
        ImageAlignment.MISALIGNED: "error",
        ImageAlignment.ORPHAN: "orphan",
        ImageAlignment.UNKNOWN: "warn",
    }

    @classmethod
    def alignment_cell(cls, alignment: ImageAlignment | None) -> str:
        """The centred, padded Up-to-date cell of an image (blank when there is
        nothing to compare)."""
        icon_key = None if alignment is None else cls.ALIGNMENT_ICON[alignment]
        return cls.icon_status_cell(icon_key, cls.UP_TO_DATE_HEADER)

    @classmethod
    def commit_text_width(cls, cell: CommitCell) -> int:
        """The display width of the cell of *cell*: its icon, then its commit."""
        return cls.ICON_WIDTH + (1 + len(cell.commit) if cell.commit else 0)

    @classmethod
    def commit_cell(cls, cell: CommitCell, width: int) -> str:
        """The cell of a commit recorded in an image: the icon of its verdict, then
        the commit, padded to *width*."""
        icon, color = ClickTheme.status_icons[cls.ALIGNMENT_ICON[cell.alignment]]
        text = click.style(icon, fg=color) + (f" {cell.commit}" if cell.commit else "")
        return text + " " * (width - cls.commit_text_width(cell))

    @classmethod
    def header(cls, name_width: int, *column_headers: str) -> str:
        """The header row: the name of the image is bold, the Up-to-date header
        follows it."""
        bold_name = click.style(f"{cls.NAME_HEADER:<{name_width}}", bold=True)
        return "  ".join(["", bold_name, cls.UP_TO_DATE_HEADER, *column_headers])

    @classmethod
    def rule(cls, name_width: int, *column_widths: int) -> str:
        total = (
            name_width
            + 2
            + len(cls.UP_TO_DATE_HEADER)
            + sum(2 + width for width in column_widths)
        )
        return "  " + "─" * total

    @classmethod
    def echo_convert_table(cls, rows: list[ConvertImageRow]) -> None:
        name_width = max(len(cls.NAME_HEADER), max(len(row.name) for row in rows))
        document_width = max(
            len(cls.DOCUMENT_HEADER),
            max(cls.commit_text_width(row.document) for row in rows),
        )
        pdf_to_markdown_width = max(
            len(cls.PDF_TO_MARKDOWN_HEADER),
            max(cls.commit_text_width(row.pdf_to_markdown) for row in rows),
        )
        click.echo(click.style(f"  {cls.CONVERT_TITLE}", bold=True))
        click.echo(
            cls.header(
                name_width,
                f"{cls.DOCUMENT_HEADER:<{document_width}}",
                cls.PDF_TO_MARKDOWN_HEADER,
            )
        )
        click.echo(cls.rule(name_width, document_width, pdf_to_markdown_width))
        for row in rows:
            click.echo(
                f"  {row.name:<{name_width}}  {cls.alignment_cell(row.summary)}  "
                f"{cls.commit_cell(row.document, document_width)}  "
                f"{cls.commit_cell(row.pdf_to_markdown, pdf_to_markdown_width)}".rstrip()
            )

    @classmethod
    def echo_other_table(cls, rows: list[OtherImageRow]) -> None:
        name_width = max(len(cls.NAME_HEADER), max(len(row.name) for row in rows))
        repository_width = max(
            len(cls.REPOSITORY_HEADER), max(len(row.repository) for row in rows)
        )
        click.echo(click.style(f"  {cls.OTHER_TITLE}", bold=True))
        click.echo(cls.header(name_width, cls.REPOSITORY_HEADER))
        click.echo(cls.rule(name_width, repository_width))
        for row in rows:
            click.echo(
                f"  {row.name:<{name_width}}  {cls.alignment_cell(row.summary)}  "
                f"{row.repository}".rstrip()
            )


@click.group(
    invoke_without_command=True, short_help="Docker images of the current role"
)
@click.pass_context
def images(ctx: click.Context) -> None:
    """Show the Docker images of the components of the current role."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(images_list)


@images.command("list")
@click.pass_context
def images_list(ctx) -> None:
    """List the local Docker images of the components of the current role and tell
    whether the commits recorded in them are the ones of the sources the ecosystem
    designates now."""
    app = ctx.find_object(AppContext)
    docker = app.component_registry.get("docker-command")
    status, message = docker.check()
    if status != "ok":
        raise click.ClickException(message)
    eco = app.component_registry.get("ecosystem")
    role = app.role_registry.detect_role()
    active = app.role_registry.active_components(role)
    components = sorted(
        (comp for comp in active if isinstance(comp, ContComp)),
        key=lambda comp: comp.name,
    )
    directories = eco.resolve_dirs()
    # A doc-steward only handles the document of the current directory
    document_repos = (
        [eco.cwd_doc_repo()]
        if app.role_registry.role_is_doc_steward_family(role)
        else eco.discover_doc_repos(directories)
    )
    listing = ImageListing(
        eco,
        docker,
        directories,
        {name: Path(path_str) for name, _, path_str, _ in document_repos},
        _catalog_document_names(),
    )
    convert_rows = listing.convert_rows(components)
    other_rows = listing.other_rows(components)
    if not convert_rows and not other_rows:
        click.echo(
            click.style(
                "    No Docker images of the components of the current role.",
                fg="yellow",
            )
        )
        return
    if convert_rows:
        _ImagesTable.echo_convert_table(convert_rows)
    if convert_rows and other_rows:
        click.echo()
    if other_rows:
        _ImagesTable.echo_other_table(other_rows)


def _catalog_document_names() -> set[str]:
    """The names of the documents listed by the catalog (none without a readable
    catalog)."""
    catalog_path = CatalogFile.resolve_path()
    if not catalog_path.is_file():
        return set()
    try:
        return set(CatalogFile(catalog_path).names())
    except ValueError:
        return set()
