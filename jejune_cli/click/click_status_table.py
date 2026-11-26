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


class ComponentStatusTable(StatusTable):
    """What the tables of `ecosystem status` share: the placeholders standing for
    the directories listed in the header, and the Up-to-date / Commit cells."""

    LOCATION_LABEL = {
        "root": "[JEJUNE_ROOT_DIR]",
        "tmp": "[ECOSYSTEM_DIR]",
        "cwd": "[CWD]",
    }
    REPO_ROOT_LABEL = "[REPO_ROOT_DIR]"
    COMMIT_HEADER = "Commit"

    @staticmethod
    def remote_label(remote_url: str, repo_root_dir: str) -> str:
        """*remote_url* with its REPO_ROOT_DIR prefix replaced by its placeholder."""
        if remote_url.startswith(repo_root_dir):
            return ComponentStatusTable.REPO_ROOT_LABEL + remote_url[len(repo_root_dir) :]
        return remote_url

    @staticmethod
    def location_label(state, repo_root_dir: str) -> str:
        """The placeholder of the directory of the local repository *state* or, when it
        is only remote, its url."""
        if state.location.is_local:
            return ComponentStatusTable.LOCATION_LABEL[state.location.tier]
        return ComponentStatusTable.remote_label(state.remote_url, repo_root_dir)

    @staticmethod
    def icon_cell(ok: bool, icon_header: str) -> str:
        """The ✓/✗ cell, centred under *icon_header*."""
        icon, color = ClickTheme.status_icons["ok" if ok else "error"]
        pad = (len(icon_header) - ComponentStatusTable.ICON_WIDTH) // 2
        trail = len(icon_header) - pad - ComponentStatusTable.ICON_WIDTH
        return f"{'':>{pad}}{click.style(icon, fg=color)}{'':<{trail}}"

    @staticmethod
    def header(
        first,
        icon_header,
        location_header,
        first_width,
        location_width,
        commit_width: int = len(COMMIT_HEADER),
    ) -> str:
        """The header row: *first* is bold and *location_header* is centred."""
        bold_first = click.style(f"{first:<{first_width}}", bold=True)
        row = (
            f"  {bold_first}  {icon_header}  "
            f"{location_header:^{location_width}}  "
            f"{ComponentStatusTable.UP_TO_DATE_HEADER}  "
        )
        return f"{row}{ComponentStatusTable.COMMIT_HEADER}"

    @staticmethod
    def rule(first_width, icon_header, location_width, commit_width) -> str:
        total = (
            first_width
            + 2
            + len(icon_header)
            + 2
            + location_width
            + 2
            + len(ComponentStatusTable.UP_TO_DATE_HEADER)
            + 2
            + commit_width
        )
        return "  " + "─" * total
