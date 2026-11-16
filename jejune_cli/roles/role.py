"""Role dataclass for jejune_cli."""

from dataclasses import dataclass
from typing import Callable, ClassVar


@dataclass
class Role:
    NONE: ClassVar["Role"]

    name: str
    component_names: tuple[str, ...]
    includes: tuple[str, ...]
    section_title: str
    detector: Callable[[], bool] | None = None
    description: str = ""
    is_abstract: bool = False
    extra_commands: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.name)


Role.NONE = Role(name="", component_names=(), includes=(), section_title="")
