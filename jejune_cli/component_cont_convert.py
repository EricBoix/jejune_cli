"""convert containerized component."""
from .component_containerized import cont_comp
from .configuration import configuration
from .component_registry import REGISTRY
from .convert import validate_convert_dir


class comp_convert(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="convert",
            image_name="jejune-convert",
            dependencies=["pypi-server"],
            hint="run `jejune convert build`",
            configuration=configuration(
                "set CONVERT_DOC_DIR in .jejune/env-config",
                env_vars=["CONVERT_DOC_DIR"],
                env_var_validator=validate_convert_dir,
            ),
        )

    def build(self, no_cache: bool = False) -> None:
        from .convert import _build_if_configured
        _build_if_configured(no_cache=no_cache)

    def is_built(self) -> bool:
        from .convert import image_built
        return image_built()[0]

    def is_running(self) -> tuple[bool, str]:
        from .convert import convert_configured, image_built
        if not convert_configured():
            return True, ""
        built, msg = image_built()
        return built, msg

    def check(self) -> tuple[str, str]:
        from .convert import convert_configured
        if not convert_configured():
            return "ok", ""
        ok, msg = self.is_running()
        return ("ok", "") if ok else ("warn", msg)


convert_comp = comp_convert()
REGISTRY.add(convert_comp)
