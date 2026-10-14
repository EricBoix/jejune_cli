"""ProductionCommand — suppress heuristic next-steps for read-only commands."""
from __future__ import annotations

import click

from .app_context import AppContext


class ProductionCommand(click.Command):
    """A Command that suppresses the post-invoke `jejune next` display.

    Intended for observation/read-only commands where showing next steps
    would be noise rather than guidance (e.g. `jejune neo4j stats`,
    `jejune neo4j llm`).

    Usage::

        @neo4j.command("stats", cls=ProductionCommand)
        ...
    """

    def invoke(self, ctx: click.Context) -> object:
        result = super().invoke(ctx)
        app = ctx.find_object(AppContext)
        if app is not None:
            app.heuristic_step_registry.mark_printed()
        return result
