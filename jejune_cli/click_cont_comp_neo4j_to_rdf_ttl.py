"""Click commands for the neo4j-to-RDF/Turtle component."""
from pathlib import Path

import click

from .app_context import AppContext


@click.command("dump-turtle")
@click.argument("output_dir", type=click.Path())
@click.argument("filename")
@click.pass_context
def dump_turtle(ctx, output_dir, filename):
    """Export the Neo4j knowledge graph to OUTPUT_DIR/FILENAME (RDF/Turtle).

    Requires a running Neo4j instance populated by `jejune graph extract`.
    Neo4j credentials are read from .jejune/env-secrets / environment.
    """
    app = ctx.find_object(AppContext)
    neo4j_to_rdf_ttl_comp = app.component_registry.get("neo4j-to-rdf-ttl")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Building {neo4j_to_rdf_ttl_comp.image_name} ...")
    neo4j_to_rdf_ttl_comp.build()

    click.echo(f"Exporting to {output_dir / filename} ...")
    neo4j_to_rdf_ttl_comp.dump_turtle(output_dir, filename)
