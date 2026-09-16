"""LLM observability server component."""
import os
import urllib.error
import urllib.request

from .configuration import configuration
from .configuration_entry import configuration_entry
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
                configuration_entry("TRACELOOP_BASE_URL",
                    hint="configure TRACELOOP_BASE_URL in .jejune/env-config",
                    source_file=".jejune/env-config"),
            ),
        )

    @property
    def container_name(self) -> str:
        return "jejune_llm_observability"

    def available(self) -> tuple[bool, str]:
        cfg_status, *_ = self.configuration.check()
        if cfg_status != "ok":
            return False, "not configured"
        return self.is_running()

    def otlp_base_url(self) -> str:
        return os.environ.get("TRACELOOP_BASE_URL", f"http://localhost:{self.otlp_port}")

    def check_endpoint_reachable(self) -> tuple[bool, str]:
        url = self.otlp_base_url()
        try:
            with urllib.request.urlopen(url, timeout=5):
                return True, url
        except urllib.error.HTTPError:
            return True, url
        except urllib.error.URLError:
            return False, url

    def check(self) -> tuple[str, str]:
        cfg_status, *_ = self.configuration.check()
        if cfg_status != "ok":
            return "warn", "not configured"
        ok, msg = self.is_running()
        return ("ok", "") if ok else ("warn", msg)
