"""Manifest configuration component."""
from .component_internal import component
from .component_registry import REGISTRY


class comp_manifest(component):
    def __init__(self) -> None:
        super().__init__(name="manifest")

    def check_config(self) -> tuple[str, str] | None:
        from pathlib import Path
        from .test import _manifest_config_status
        return _manifest_config_status(Path.cwd())

    def check(self) -> tuple[str, str]:
        from pathlib import Path
        from .test import _manifest_avail_status, _manifest_config_status
        cfg_status, cfg_msg = _manifest_config_status(Path.cwd())
        avail_status, avail_msg = _manifest_avail_status(Path.cwd())
        if cfg_status == "error" and avail_status == "ok":
            return cfg_status, cfg_msg
        return avail_status, avail_msg


REGISTRY.add(comp_manifest())
