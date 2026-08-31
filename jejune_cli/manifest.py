"""`jejune manifest` command group — per-document manifest operations."""

import re
import sys
from pathlib import Path

import click
import yaml

from ._doctor import _STATUS_FG


@click.group("manifest", short_help="Document manifest operations")
def manifest():
    """Validate and inspect the document manifest (manifest.yaml) in the current repo."""


@manifest.command("check")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Print referenced files.")
def manifest_check(verbose):
    """Validate manifest.yaml in the current repository.

    Required-field errors exit 1. Unknown-field warnings exit 0.
    File-reference errors exit 1.
    """
    from .test import _check_doc_yaml, _manifest_avail_status, _manifest_config_status
    cfg_status, cfg_msg = _manifest_config_status(Path.cwd())
    avail_status, avail_msg = _manifest_avail_status(Path.cwd())
    failed = False
    if cfg_status == "error":
        click.echo(click.style(f"  {cfg_msg}", fg="red"))
        failed = True
    elif cfg_status == "warn":
        click.echo(click.style(f"  {cfg_msg}", fg="yellow"))
    if avail_status != "ok":
        click.echo(click.style(f"  {avail_msg}", fg="yellow"))
        failed = True
    if failed:
        click.echo(click.style("manifest.yaml — error(s)", fg="red"))
        sys.exit(1)
    if cfg_status == "warn":
        click.echo(click.style("manifest.yaml — warning(s)", fg="yellow"))
        return
    if verbose:
        _, file_refs = _check_doc_yaml(Path.cwd())
        if file_refs:
            key_width = max(len(k) for k, _ in file_refs)
            for key, rel in file_refs:
                click.echo(f"  {key:<{key_width}}  {rel}")
    click.echo(click.style("manifest.yaml — ok", fg="green"))


@manifest.command("check-config")
def manifest_check_config():
    """Show manifest.yaml configuration detail (required fields, unknown fields)."""
    from .test import _manifest_config_status
    status, msg = _manifest_config_status(Path.cwd())
    fg = _STATUS_FG.get(status, "white")
    click.echo(f"  manifest.yaml  {click.style(status, fg=fg)}")
    if msg:
        click.echo(f"  {msg}")


@manifest.command("status-config")
def manifest_status_config():
    """Show manifest configuration status."""
    from .test import _manifest_config_status
    status, _ = _manifest_config_status(Path.cwd())
    click.echo(f"manifest: {click.style(status, fg=_STATUS_FG.get(status, 'white'))}")


@manifest.command("hint-config")
def manifest_hint_config():
    """Show the configuration hint for the manifest component."""
    from .test import _manifest_config_status
    status, _ = _manifest_config_status(Path.cwd())
    if status == "ok":
        click.echo(click.style("manifest.yaml is properly configured", fg="green"))
    else:
        click.echo("run `jejune manifest check`")


@manifest.command("check-availability")
def manifest_check_availability():
    """Show manifest availability detail (file references exist on disk)."""
    from .test import _manifest_avail_status
    status, msg = _manifest_avail_status(Path.cwd())
    label = "ok" if status == "ok" else msg
    click.echo(f"  files  {click.style(label, fg=_STATUS_FG.get(status, 'white'))}")


@manifest.command("status-availability")
def manifest_status_availability():
    """Show manifest availability status."""
    from .test import _manifest_avail_status
    status, _ = _manifest_avail_status(Path.cwd())
    click.echo(f"manifest: {click.style(status, fg=_STATUS_FG.get(status, 'white'))}")


@manifest.command("hint-availability")
def manifest_hint_availability():
    """Show how to fix manifest availability issues."""
    from .test import _manifest_avail_status
    status, _ = _manifest_avail_status(Path.cwd())
    if status == "ok":
        click.echo(click.style("all manifest file references found", fg="green"))
    else:
        click.echo("run `jejune manifest check-availability`")


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
