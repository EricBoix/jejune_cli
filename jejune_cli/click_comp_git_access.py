"""The `jejune git-access` command group."""

import os
from pathlib import Path

import click
import yaml

from .app_context import AppContext
from .click_configuration import (
    print_config_check,
    print_config_hint,
    print_config_status,
)
from .component_git_access import CompGitAccess


@click.group(short_help="Git authentication to repositories")
@click.pass_context
def git_access(ctx):
    """Manage how git authenticates to repository URLs."""
    ctx.obj = ctx.find_object(AppContext).component_registry.get("git-access")


@git_access.command("check-config")
@click.pass_obj
def check_config(comp):
    """Show per-variable configuration detail for the git-access component."""
    print_config_check(comp.configuration)


@git_access.command("status-config")
@click.pass_obj
def status_config(comp):
    """Show git-access configuration status."""
    print_config_status(comp.configuration)


@git_access.command("hint-config")
@click.pass_obj
def hint_config(comp):
    """Show the configuration hint for the git-access component."""
    print_config_hint(comp.configuration)


class CatalogAccessChecker:
    """Cross-checks the entries of a catalog.yaml with their access-key files."""

    def __init__(self, comp: CompGitAccess, catalog_path: Path) -> None:
        self._comp = comp
        self._catalog_path = catalog_path

    def run(self) -> list[tuple[str, str, str]]:
        """Return (status, subject, message) rows; status is ok, warn or error."""
        if not self._catalog_path.is_file():
            return [("error", str(self._catalog_path), "catalog file not found")]
        try:
            data = yaml.safe_load(self._catalog_path.read_text()) or {}
        except yaml.YAMLError as exc:
            return [("error", str(self._catalog_path), f"invalid YAML: {exc}")]
        documents = data.get("documents", []) if isinstance(data, dict) else None
        if not isinstance(documents, list):
            return [("error", str(self._catalog_path), "no `documents` list")]
        rows = []
        for index, document in enumerate(documents, 1):
            rows.extend(self._check_document(index, document))
        if not rows:
            rows.append(("ok", str(self._catalog_path), "no document entries"))
        return rows

    def _check_document(self, index: int, document) -> list[tuple[str, str, str]]:
        if not isinstance(document, dict) or "url" not in document:
            return [("error", f"entry #{index}", "entry without a `url`")]
        url = document["url"]
        public = document.get("public", True)
        token_file = document.get("token_file")
        if public:
            if token_file:
                return [
                    ("warn", url, "public entry has a `token_file`, which is unused")
                ]
            return [("ok", url, "public")]
        if token_file:
            status, message = self._comp.validate_token_file(str(token_file))
            return [(status, url, message or f"private, token file {token_file}")]
        try:
            resolved = self._comp.resolve_credentials()
        except ValueError as exc:
            return [("error", url, str(exc))]
        if resolved is None:
            return [
                (
                    "error",
                    url,
                    "private entry without `token_file` and "
                    f"neither {self._comp.TOKEN_ENV_VAR} nor "
                    f"{self._comp.TOKEN_FILE_ENV_VAR} is set",
                )
            ]
        return [("ok", url, "private, default credentials from the environment")]


@git_access.command("check-configuration")
@click.option(
    "--catalog",
    "catalog_option",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Catalog file to check (default: $JEJUNE_CATALOG or ./catalog.yaml).",
)
@click.pass_obj
def check_configuration(comp, catalog_option):
    """Check that catalog.yaml and the access-key files it points to agree and are valid.

    A private entry (`public: false`) needs a valid token file: its own
    `token_file`, else the one of the environment. Exits 1 on any error.
    """
    catalog_path = catalog_option or Path(
        os.environ.get("JEJUNE_CATALOG") or Path.cwd() / "catalog.yaml"
    )
    rows = CatalogAccessChecker(comp, catalog_path).run()
    subject_width = max(len(subject) for _, subject, _ in rows)
    colors = {"ok": "green", "warn": "yellow", "error": "red"}
    for status, subject, message in rows:
        label = click.style(f"{status:<5}", fg=colors[status])
        click.echo(f"  {label}  {subject:<{subject_width}}  {message}")
    if any(status == "error" for status, _, _ in rows):
        raise SystemExit(1)
