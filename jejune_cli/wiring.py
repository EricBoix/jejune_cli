"""Central assembly — import all wiring modules in dependency order."""
from . import component_wiring       # noqa: F401  1. populate ComponentRegistry
from . import role_wiring            # noqa: F401  2. register built-in roles
from . import heuristic_step_wiring  # noqa: F401  3. register heuristics (needs 1)
from . import plugin_cli_wiring      # noqa: F401  4. import CLI setup (needs 1, 2, 3)
