"""The cells the status tables of the CLI share (`ecosystem status`, `images list`)."""

import click

from jejune_cli.click.click_theme import ClickTheme


class StatusTable:
    """The centred icon cells (✓/✗/…) of a table."""

    ICON_WIDTH = 1  # display width of ✓/✗
    UP_TO_DATE_HEADER = "Up-to-date"

    @classmethod
    def status_cell(cls, status: bool | None, header: str) -> str:
        """The ✓/✗ cell (blank when *status* is None), centred under *header*."""
        if status is None:
            return cls.icon_status_cell(None, header)
        return cls.icon_status_cell("ok" if status else "error", header)

    @classmethod
    def icon_status_cell(cls, icon_key: str | None, header: str) -> str:
        """The cell of the `ClickTheme.status_icons` entry *icon_key* (blank when it
        is None), centred under *header*."""
        if icon_key is None:
            icon, color = "", ""
        else:
            icon, color = ClickTheme.status_icons[icon_key]
        cell = click.style(icon, fg=color) if color else ""
        pad = (len(header) - cls.ICON_WIDTH) // 2
        trail = len(header) - pad - cls.ICON_WIDTH
        # Unstyled blanks of the icon width when there is no icon
        icon_blank = "" if cell else " " * cls.ICON_WIDTH
        return f"{'':>{pad}}{cell}{icon_blank}{'':<{trail}}"

    @classmethod
    def up_to_date_cell(cls, up_to_date: bool | None) -> str:
        """The centred, padded Up-to-date cell."""
        return cls.status_cell(up_to_date, cls.UP_TO_DATE_HEADER)
