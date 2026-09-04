"""LLM observability server component."""
from .configuration import configuration
from .component_ext_server import ext_server
from .component_registry import REGISTRY


class comp_server_llm_observability(ext_server):
    def __init__(self) -> None:
        super().__init__(
            name="llm-observability",
            api_url="",
            hint="run `jejune llm-observability start`",
            configuration=configuration(
                "configure TRACELOOP_BASE_URL in .jejune/env-config",
                env_vars=["TRACELOOP_BASE_URL"],
            ),
        )

    def check(self) -> tuple[str, str]:
        from .llm_observability import llm_observability_available
        ok, msg = llm_observability_available()
        return ("ok", "") if ok else ("warn", msg)


llm_obs_comp = comp_server_llm_observability()
REGISTRY.add(llm_obs_comp)
