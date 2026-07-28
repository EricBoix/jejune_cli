"""Developer role: configuration data."""

CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {
    "developer": (["JEJUNE_ROOT_DIR"], "ecosystem root"),
}

COMPONENT_CONFIG_HINTS: dict[str, str] = {
    "developer": "export JEJUNE_ROOT_DIR=/path/to/your/jejune/ecosystem",
}
