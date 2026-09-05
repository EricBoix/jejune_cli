"""LLM server component."""
from .configuration import configuration
from .component_ext_server import ext_server


class comp_server_llm(ext_server):
    def __init__(self) -> None:
        super().__init__(
            name="llm",
            api_url="",
            dependencies=[type(self).registry.get("network")],
            hint="run `jejune llm status-config`",
            configuration=configuration(
                "edit .jejune/env-secrets",
                env_vars=["LLM_MODEL_URL", "LLM_API_KEY", "LLM_MODEL_NAME"],
            ),
        )
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        from .llm import llm_check_availability
        ok, msg = llm_check_availability()
        if ok:
            return "ok", ""
        return "warn" if msg == "not configured" else "error", msg


llm_comp = comp_server_llm()
