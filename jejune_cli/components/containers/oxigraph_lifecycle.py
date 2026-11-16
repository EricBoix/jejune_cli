"""How the Oxigraph container lifecycle is owned in a given workspace."""

from enum import Enum


class OxigraphLifecycle(Enum):
    STANDALONE = "standalone"  # doc-steward: `jejune oxigraph start` / `stop`
    COMPOSE_MANAGED = "compose-managed"  # deployer: `jejune up` / `jejune down`
