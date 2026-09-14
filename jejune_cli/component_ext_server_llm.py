"""LLM server component."""
from .configuration import configuration
from .configuration_entry import configuration_entry
from .component_ext_server import ext_server
from .component_registry import ComponentRegistry


class comp_server_llm(ext_server):
    def __init__(self) -> None:
        super().__init__(
            name="llm",
            api_url="",
            dependencies=[ComponentRegistry().get("network")],
            hint="run `jejune llm status-config`",
            configuration=configuration(
                configuration_entry("LLM_MODEL_URL",  hint="edit .jejune/env-secrets", source_file=".jejune/env-secrets"),
                configuration_entry("LLM_API_KEY",    hint="edit .jejune/env-secrets", source_file=".jejune/env-secrets"),
                configuration_entry("LLM_MODEL_NAME", hint="edit .jejune/env-secrets", source_file=".jejune/env-secrets"),
            ),
        )

    def check(self) -> tuple[str, str]:
        from .llm import llm_check_availability
        ok, msg = llm_check_availability()
        if ok:
            return "ok", ""
        return "warn" if msg == "not configured" else "error", msg


