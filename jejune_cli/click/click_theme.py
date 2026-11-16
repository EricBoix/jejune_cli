"""Shared visual theme: status colours and icons for CLI output."""


class ClickTheme:
    status_foregrounds: dict[str, str] = {
        "ok": "green",
        "warn": "yellow",
        "error": "red",
    }
    status_icons: dict[str, tuple[str, str]] = {
        "ok": ("✓", "green"),
        "warn": ("–", "yellow"),
        "error": ("✗", "red"),
    }
