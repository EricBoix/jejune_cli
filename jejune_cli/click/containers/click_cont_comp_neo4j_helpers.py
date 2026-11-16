"""Click-level helpers shared by Neo4j commands."""

import os
import re
import shutil
from pathlib import Path

import click

_NEO4J_DUMP_FILENAME_MAX_LENGTH = 63


def decorate_dump_filename(
    dump_filename: str,
    llm_model_names: list[str],
    max_length: int | None = _NEO4J_DUMP_FILENAME_MAX_LENGTH,
) -> tuple[str, bool]:
    """Decorate dump_filename with LLM model names.

    When max_length is not None, raises ValueError if stem+suffix alone exhaust
    the limit, and truncates the decoration to fit.  When max_length is None,
    no length constraint is enforced (use for non-Neo4j output formats).
    """
    safe_models = "_".join(re.sub(r"[^\w\-]", "_", name) for name in llm_model_names)
    stem = Path(dump_filename).stem
    suffix = Path(dump_filename).suffix
    if max_length is not None:
        available = max_length - len(stem) - 1 - len(suffix)
        if available <= 0:
            raise ValueError(
                f"'{dump_filename}' stem+suffix already fills the "
                f"{max_length}-char Neo4j limit; "
                "cannot append LLM model decoration."
            )
        truncated = len(safe_models) > available
        return f"{stem}.{safe_models[:available]}{suffix}", truncated
    return f"{stem}.{safe_models}{suffix}", False


def resolve_restore_dump_location(
    results_dir: Path, dump_argument: str, temporary_directory: Path
) -> tuple[Path | None, str]:
    """Resolve where a restore dump lives; return (backups_dir, dump_filename).

    A simple filename (no directory separator) is looked up in
    results_dir/backups: backups_dir is None, meaning "use the default".
    A path-filename is relative to the current directory. When it does not
    already sit in results_dir/backups, the dump is copied into
    temporary_directory (which then becomes the mounted backups_dir).
    """
    if os.sep not in dump_argument:
        return None, dump_argument

    dump_path = (Path.cwd() / dump_argument).resolve()
    if not dump_path.is_file():
        raise click.ClickException(f"Dump file not found: {dump_path}")
    if dump_path.parent == (results_dir / "backups").resolve():
        return None, dump_path.name

    click.echo(f"Copying {dump_path} to {temporary_directory} ...")
    shutil.copy2(dump_path, temporary_directory / dump_path.name)
    return temporary_directory, dump_path.name


def get_llm_model_names(neo4j_comp) -> list[str]:
    """Query LLM model names from Neo4j and raise ClickException on failure."""
    try:
        return neo4j_comp.query_llm_model_names()
    except RuntimeError as error:
        raise click.ClickException(str(error))


def resolve_llm_decorated_filename(
    neo4j_comp, filename: str, enforce_neo4j_limit: bool = True
) -> str:
    """Query LLM model names from Neo4j, report them, and return the decorated filename.

    Set enforce_neo4j_limit=False for output formats (e.g. Turtle) where the
    63-char Neo4j database-name limit does not apply.
    """
    max_length = _NEO4J_DUMP_FILENAME_MAX_LENGTH if enforce_neo4j_limit else None
    llm_model_names = get_llm_model_names(neo4j_comp)
    if llm_model_names:
        click.echo(f"LLM model(s): {', '.join(llm_model_names)}")
        try:
            decorated_filename, was_truncated = decorate_dump_filename(
                filename, llm_model_names, max_length=max_length
            )
        except ValueError as error:
            raise click.ClickException(str(error))
        if was_truncated:
            click.echo(
                f"Warning: LLM model decoration truncated to fit the "
                f"{_NEO4J_DUMP_FILENAME_MAX_LENGTH}-char Neo4j limit.",
                err=True,
            )
        return decorated_filename
    click.echo(
        "Warning: no llm_model_name attribute found; filename not decorated.",
        err=True,
    )
    return filename
