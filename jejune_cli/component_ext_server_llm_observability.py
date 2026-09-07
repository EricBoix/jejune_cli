"""LLM observability server component."""
from .configuration import configuration
from .component_containerized import cont_comp


class comp_server_llm_observability(cont_comp):
    mandatory = False
    otlp_port: int = 4318
    ui_port: int = 16686

    def __init__(self) -> None:
        super().__init__(
            name="llm-observability",
            image_name="jaegertracing/all-in-one",
            hint="run `jejune llm-observability start`",
            configuration=configuration(
                "configure TRACELOOP_BASE_URL in .jejune/env-config",
                env_vars=["TRACELOOP_BASE_URL"],
            ),
        )

    @property
    def container_name(self) -> str:
        return "jejune_llm_observability"

    def check(self) -> tuple[str, str]:
        cfg_status, *_ = self.configuration.check()
        if cfg_status != "ok":
            return "warn", "not configured"
        ok, msg = self.is_running()
        return ("ok", "") if ok else ("warn", msg)
