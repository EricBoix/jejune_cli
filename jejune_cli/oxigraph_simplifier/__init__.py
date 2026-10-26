"""Simplify the knowledge graph held in an Oxigraph store (no jejune_cli dependency)."""

from .oxigraph_simplifier import OxigraphSimplifier
from .simplification import Simplification, SimplificationReport

__all__ = ["OxigraphSimplifier", "Simplification", "SimplificationReport"]
