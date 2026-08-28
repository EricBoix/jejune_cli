"""Contributor role: configuration data."""

CONFIG_GROUPS: dict[str, tuple] = {
    "ecosystem": (["JEJUNE_ROOT_DIR"], "ecosystem root", "warn"),
}

COMPONENT_CONFIG_HINTS: dict[str, str] = {
    "ecosystem": "edit .jejune/ecosystem-env-config and set JEJUNE_ROOT_DIR",
}
