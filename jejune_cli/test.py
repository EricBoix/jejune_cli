import os
import subprocess
import sys
from pathlib import Path

import click
import yaml

from ._env import dot_jejune

_TMP_PATTERN = ".jejune/tmp/"
_SCHEMA_PATH = Path(__file__).parent / "schema" / "doc.yaml"


def _load_doc_schema() -> dict:
    return yaml.safe_load(_SCHEMA_PATH.read_text())


def _ensure_gitignored() -> None:
    gitignore = dot_jejune().parent / ".gitignore"
    if gitignore.exists():
        if any(l.strip() == _TMP_PATTERN for l in gitignore.read_text().splitlines()):
            return
        with gitignore.open("a") as f:
            f.write(f"{_TMP_PATTERN}\n")
    else:
        gitignore.write_text(f"{_TMP_PATTERN}\n")


def _tmp_dir() -> Path:
    tmp = dot_jejune() / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    _ensure_gitignored()
    return tmp


def _check_doc_yaml(
    repo_dir: Path,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (errors, file_refs).

    file_refs: (key, rel_path) for every file_field present in doc.yaml.
    errors: non-empty when doc.yaml is missing or a referenced file is absent.
    """
    doc_yaml = repo_dir / "doc.yaml"
    if not doc_yaml.exists():
        return [f"doc.yaml missing (see {_SCHEMA_PATH} for the expected format)"], []

    schema = _load_doc_schema()
    data = yaml.safe_load(doc_yaml.read_text()) or {}
    errors: list[str] = []
    file_refs: list[tuple[str, str]] = []

    for field in schema.get("required_fields", {}):
        if field not in data:
            errors.append(f"required field {field!r} missing")

    for key in schema.get("file_fields", []):
        rel = data.get(key)
        if rel is None:
            continue
        file_refs.append((key, rel))
        if not (repo_dir / rel).exists():
            errors.append(f"{key}: {rel!r} not found")

    if errors:
        errors.append(f"see {_SCHEMA_PATH} for the expected format")
    return errors, file_refs


@click.command("test")
@click.option(
    "--catalog",
    envvar="JEJUNE_CATALOG",
    default=None,
    type=click.Path(),
    help="Path to a catalog.yaml (default: $JEJUNE_CATALOG, then .jejune/catalog.yaml).",
)
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
def test_cmd(catalog, root_dir, repo, verbose):
    """Validate jejune_doc_* repositories found in the catalog.

    Repositories are expected under ROOT_DIR/<name>/. Missing repositories
    (or all when ROOT_DIR is unset) are cloned into .jejune/tmp/ which is
    gitignored automatically.

    For each repository, doc.yaml is parsed and every file it references is
    checked for existence. Exits with a non-zero status if any check fails.
    """
    if catalog is None:
        default = dot_jejune() / "catalog.yaml"
        if not default.exists():
            raise click.ClickException(
                "No catalog specified. Set $JEJUNE_CATALOG, use --catalog, "
                "or run `jejune configure init` to create .jejune/catalog.yaml."
            )
        catalog = str(default)

    root = Path(root_dir) if root_dir else None
    if root is not None and not root.exists():
        source = (
            "$JEJUNE_ROOT_DIR"
            if os.environ.get("JEJUNE_ROOT_DIR") == root_dir
            else "--root-dir"
        )
        raise click.ClickException(f"ROOT_DIR ({source}) does not exist: {root}")

    docs = yaml.safe_load(Path(catalog).read_text())["documents"]

    if repo:
        docs = [d for d in docs if d["name"] == repo]
        if not docs:
            raise click.ClickException(f"Repository '{repo}' not found in catalog.")

    tmp: Path | None = None
    all_ok = True

    for doc in docs:
        name = doc["name"]
        url = doc["url"]

        repo_dir = root / name if root is not None else None
        if repo_dir is None or not repo_dir.exists():
            if tmp is None:
                tmp = _tmp_dir()
            repo_dir = tmp / name
            if not repo_dir.exists():
                click.echo(f"Cloning {name} ...")
                subprocess.run(["git", "clone", url, str(repo_dir)], check=True)

        cloned_label = click.style("cloned", fg="green")
        errors, file_refs = _check_doc_yaml(repo_dir)
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
