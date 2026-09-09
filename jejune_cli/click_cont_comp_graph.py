import click

from .component_registry import REGISTRY as COMP_REGISTRY
from .click_comp_configuration import print_config_hint, print_config_status

graph_comp = COMP_REGISTRY.get("graph")
llm_obs_comp = COMP_REGISTRY.get("llm-observability")

_DEP_HINTS = {
    "neo4j": "run `jejune neo4j start`",
    "llm":   "run `jejune llm status`",
}

_PREFLIGHT_SKIP = {
    "check-availability", "status-availability", "hint-availability",
    "check-config", "status-config", "hint-config",
    "view", "split", "build",
}


@click.group(short_help="Build and export the knowledge graph")
@click.pass_context
def graph(ctx):
    """Build and export the knowledge graph for the current jejune_doc_<name> repository."""
    if ctx.invoked_subcommand not in _PREFLIGHT_SKIP:
        graph_comp.preflight()


@graph.command("build")
@click.option("--no-cache", is_flag=True, default=False,
              help="Do not use Docker layer cache when building.")
def graph_build(no_cache: bool):
    """Build the knowledge-graph extraction Docker image."""
    graph_comp.build(no_cache=no_cache)


@graph.command("check-availability")
def check_availability():
    """Show graph availability status with optional-dep detail."""
    ok, msg = graph_comp.is_running()
    status = click.style("ok", fg="green") if ok else click.style(msg, fg="red")
    lo_ok, _ = llm_obs_comp.is_running()
    opt = click.style("llm-observability", fg="green" if lo_ok else "yellow")
    click.echo(f"graph: {status}  ({opt} optional)")


@graph.command("status-availability")
def status_availability():
    """Show graph availability status."""
    ok, _ = graph_comp.is_running()
    click.echo(f"graph: {click.style('ok', fg='green') if ok else click.style('error', fg='red')}")


@graph.command("hint-availability")
def hint_availability():
    """Show how to fix unavailable graph dependencies."""
    statuses = graph_comp.dep_statuses()
    failing = [dep for dep, (ok, _) in statuses.items() if not ok]
    if not failing:
        click.echo(click.style("all graph dependencies are available", fg="green"))
        return
    for dep in failing:
        click.echo(_DEP_HINTS[dep])


@graph.command("check-config")
def check_config():
    """Show per-variable configuration detail for the graph component."""
    from .click_comp_configuration import print_config_check
    print_config_check(graph_comp.configuration)


@graph.command("status-config")
def status_config():
    """Show graph configuration status."""
    print_config_status(graph_comp.configuration)


@graph.command("hint-config")
def hint_config():
    """Show the configuration hint for the graph component."""
    print_config_hint(graph_comp.configuration)


@graph.command("split", context_settings={"ignore_unknown_options": True})
@click.argument("doc_dir", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--splitter",
    type=click.Choice(list(graph_comp.SPLITTERS)),
    default="headers",
    show_default=True,
    help="Splitting strategy.",
)
@click.option("--output", default=None,
              help="Output JSON path inside the container. Defaults to the splitter's own naming scheme.")
@click.option("--no-cache", is_flag=True, default=False,
              help="Do not use Docker layer cache when building.")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def split(doc_dir, splitter, output, no_cache, extra_args):
    """Split DOC_DIR's catalog into JSON chunks.

    Builds the extraction Docker image and runs the chosen splitter script
    against /data/manifest.yaml. Without --output the splitter writes a file
    named after the markdown source and the splitting modality.

    EXTRA_ARGS are forwarded verbatim to the splitter (e.g. --output_dir /data).
    """
    graph_comp.run_split(doc_dir, splitter, output, no_cache, extra_args)


@graph.command("extract", context_settings={"ignore_unknown_options": True})
@click.argument("doc_dir", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--no-cache", is_flag=True, default=False,
              help="Do not use Docker layer cache when building.")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def extract(doc_dir, no_cache, extra_args):
    """Run the Markdown → Neo4j knowledge-graph extraction for DOC_DIR.

    DOC_DIR is the root of a jejune_doc_<name> repository. The command runs
    in two steps using the same Docker image:

    \b
    1. split_by_headers.py  -- splits /data/manifest.yaml into /data/_chunks.json
    2. extract_kg_graph.py  -- feeds the JSON into Neo4j

    EXTRA_ARGS are forwarded verbatim to the extractor (step 2), e.g.
    --load_json_document /data/other.json to blend additional pre-built JSON
    files alongside the auto-generated chunks.

    To use a different splitter or inspect chunks before extraction, run the
    splitter container step manually and call this command with the resulting
    JSON via --load_json_document.

    Requires a running Neo4j instance (`jejune neo4j start`).
    Credentials and LLM settings are read from .jejune/env-secrets / environment.
    """
    graph_comp.run_extract(doc_dir, no_cache, extra_args)
