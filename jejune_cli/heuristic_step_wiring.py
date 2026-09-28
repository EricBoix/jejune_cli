"""Assembly: import heuristic providers and register their steps into HEURISTIC_STEP_REGISTRY."""

from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY
from . import heuristics_deployer, heuristics_doc_steward, heuristics_no_role

heuristics_deployer.register_heuristics()
heuristics_doc_steward.register_heuristics()
heuristics_no_role.register_heuristics()
