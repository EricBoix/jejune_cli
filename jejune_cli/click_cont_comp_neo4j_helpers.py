"""Click-level helpers shared by Neo4j commands."""

import re
from pathlib import Path

import click

_NEO4J_DUMP_FILENAME_MAX_LENGTH = 63


def decorate_dump_filename(
    dump_filename: str, llm_model_names: list[str]
) -> tuple[str, bool]:
    """Raises ValueError if stem+suffix alone exhaust the 63-char Neo4j limit."""
    safe_models = "_".join(re.sub(r"[^\w\-]", "_", name) for name in llm_model_names)
    stem = Path(dump_filename).stem
    suffix = Path(dump_filename).suffix
    available = _NEO4J_DUMP_FILENAME_MAX_LENGTH - len(stem) - 1 - len(suffix)
    if available <= 0:
        raise ValueError(
            f"'{dump_filename}' stem+suffix already fills the "
            f"{_NEO4J_DUMP_FILENAME_MAX_LENGTH}-char Neo4j limit; "
            "cannot append LLM model decoration."
        )
    truncated = len(safe_models) > available
    return f"{stem}.{safe_models[:available]}{suffix}", truncated


def resolve_llm_decorated_filename(neo4j_comp, filename: str) -> str:
    """Query LLM model names from Neo4j, report them, and return the decorated filename."""
    try:
        llm_model_names = neo4j_comp.query_llm_model_names()
    except RuntimeError as error:
        raise click.ClickException(str(error))
    if llm_model_names:
        click.echo(f"LLM model(s): {', '.join(llm_model_names)}")
        try:
            decorated_filename, was_truncated = decorate_dump_filename(
                filename, llm_model_names
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
