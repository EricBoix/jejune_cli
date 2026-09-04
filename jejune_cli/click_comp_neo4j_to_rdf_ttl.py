"""Click commands for the neo4j-to-RDF/Turtle component."""
from pathlib import Path

import click

from .click_comp_neo4j import neo4j
from .component_cont_neo4j_to_rdf_ttl import neo4j_to_rdf_ttl_comp


@neo4j.command("dump-turtle")
@click.argument("output_dir", type=click.Path())
@click.argument("filename")
def dump_turtle(output_dir, filename):
    """Export the Neo4j knowledge graph to OUTPUT_DIR/FILENAME (RDF/Turtle).

    Requires a running Neo4j instance populated by `jejune graph extract`.
    Neo4j credentials are read from .jejune/env-secrets / environment.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Building {neo4j_to_rdf_ttl_comp.image_name} ...")
    neo4j_to_rdf_ttl_comp.build()

    click.echo(f"Exporting to {output_dir / filename} ...")
    neo4j_to_rdf_ttl_comp.dump_turtle(output_dir, filename)
