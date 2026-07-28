"""Contributor role: configuration data."""

CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {
    "ecosystem": (["JEJUNE_ROOT_DIR"], "ecosystem root"),
}

COMPONENT_CONFIG_HINTS: dict[str, str] = {
    "ecosystem": "edit .jejune/ecosystem-env-config: set JEJUNE_ROOT_DIR=/path/to/your/jejune/ecosystem",
}
