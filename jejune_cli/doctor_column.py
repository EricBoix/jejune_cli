"""Column abstraction for the doctor and availability tables."""


class Column:
    def __init__(
        self,
        header: str,
        cells: dict[str, tuple[str, str]],
        styled_keys: dict[str, str] | None = None,
    ) -> None:
        """cells: component_name → (display_text, styled_text).
        display_text drives width calculation; styled_text is echoed.
        styled_keys: optional plain_comp → styled_comp mapping used by items()."""
        self.header = header
        self._cells = cells
        self._styled_keys = styled_keys or {}

    @property
    def width(self) -> int:
        return max(
            len(self.header),
            max((len(display) for display, _ in self._cells.values()), default=0),
        )

    def render_header(self) -> str:
        return f"{self.header:<{self.width}}"

    def render_cell(self, component: str) -> str:
        display, styled = self._cells.get(component, ("", ""))
        return styled + " " * (self.width - len(display))

    def items(self) -> list[tuple[str, str]]:
        """(key, styled_text) pairs for two-column subcommand tables.
        key is styled_keys[comp] when present, otherwise the plain component name."""
        return [
            (self._styled_keys.get(comp, comp), styled)
            for comp, (_, styled) in self._cells.items()
        ]

    def non_empty_items(self) -> list[tuple[str, str]]:
        """items() filtered to pairs where display_text is non-empty."""
        return [
            (self._styled_keys.get(comp, comp), styled)
            for comp, (display, styled) in self._cells.items()
            if display
        ]
