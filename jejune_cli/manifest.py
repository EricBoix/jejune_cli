"""`jejune manifest` command group — per-document manifest operations."""

import re
import sys
from pathlib import Path

import click
import yaml


@click.group("manifest", short_help="Document manifest operations")
def manifest():
    """Validate and inspect the document manifest (manifest.yaml) in the current repo."""


@manifest.command("check")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Print referenced files.")
def manifest_check(verbose):
    """Validate manifest.yaml in the current repository.

    Checks required fields, optional fields, and file references.
    Exits with a non-zero status if any check fails.
    """
    from .test import _check_doc_yaml
    errors, file_refs = _check_doc_yaml(Path.cwd())
    if errors:
        for err in errors:
            click.echo(f"  {click.style(err, fg='red')}")
        n = len([e for e in errors if "see " not in e])
        click.echo(click.style(f"manifest.yaml — {n} error(s)", fg="red"))
        sys.exit(1)
    if verbose and file_refs:
        key_width = max(len(k) for k, _ in file_refs)
        for key, rel in file_refs:
            click.echo(f"  {key:<{key_width}}  {rel}")
    click.echo(click.style("manifest.yaml — ok", fg="green"))


@manifest.command("sample")
def manifest_sample():
    """Copy the built-in manifest template to manifest.yaml in the current directory."""
    target = Path.cwd() / "manifest.yaml"
    if target.exists():
        click.echo(
            click.style(f"Warning: {target} already exists — not overwriting.", fg="yellow"),
            err=True,
        )
        return
    _TEMPLATE = (
        'title: "Document Title"\n'
        "authors:\n"
        '  - "Author Name"\n'
        "year: 2024\n"
        "keywords:\n"
        "  - keyword1\n"
        "  - keyword2\n"
        "# Optional:\n"
        "# isbn: \"978-...\"\n"
        "# File references (repo-relative paths):\n"
        "# pdf_file: original_data/document.pdf\n"
        "# markdown_file: result_data/document.md\n"
        "# sentences_file: result_data/sentences.json\n"
        "# turtle_file: result_data/graph.ttl\n"
    )
    target.write_text(_TEMPLATE)
    click.echo(f"Created {target}")


@manifest.command("slug")
@click.argument("manifest_file", required=False, default=None,
                type=click.Path())
@click.option(
    "--full-catalog", "full_catalog_path",
    default=None, type=click.Path(),
    help="Path to full-catalog.yaml (consult for slug uniqueness).",
)
def manifest_slug(manifest_file, full_catalog_path):
    """Compute a doc_name slug from manifest.yaml.

    MANIFEST_FILE defaults to manifest.yaml in the current directory.
    The slug is derived from the document's title (extended with author
    or isbn only when needed for uniqueness).
    """
    if manifest_file is None:
        manifest_file = Path.cwd() / "manifest.yaml"
    src = Path(manifest_file)
    if not src.exists():
        raise click.ClickException(f"not found: {src}")
    doc = yaml.safe_load(src.read_text())
    title = doc.get("title", "")
    authors = doc.get("authors", [])
    isbn = doc.get("isbn") or ""

    existing: set[str] = set()
    if full_catalog_path:
        full_cat = Path(full_catalog_path)
        if full_cat.exists():
            for entry in yaml.safe_load(full_cat.read_text()).get("documents", []):
                if "doc_name" in entry:
                    existing.add(entry["doc_name"])

    def _slugify(text: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return re.sub(r"-{2,}", "-", s)

    main_title = re.split(r"[:—]", title, maxsplit=1)[0].strip()
    first_author = authors[0] if authors else ""
    candidates = [
        _slugify(main_title),
        _slugify(f"{main_title} {first_author}") if first_author else None,
        _slugify(f"{main_title} {first_author} {isbn}") if first_author or isbn else None,
        _slugify(f"{title} {first_author} {isbn}"),
    ]

    for candidate in candidates:
        if candidate and candidate not in existing:
            click.echo(candidate)
            return

    raise click.ClickException(
        "Could not generate a unique slug — all candidates exist in full-catalog.yaml."
    )
