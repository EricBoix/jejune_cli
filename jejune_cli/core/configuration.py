"""configuration: aggregate container for ConfigurationEntry instances."""

from pathlib import Path

from jejune_cli.core.configuration_entry import ConfigurationEntry


class Configuration:
    def __init__(
        self, *entries: ConfigurationEntry, failure_hint: str | None = None
    ) -> None:
        self.entries: list[ConfigurationEntry] = list(entries)
        # When set, replaces the per-entry hints: it points the user at a
        # diagnostic command instead of listing every file of every entry.
        self.failure_hint = failure_hint

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def check(self) -> tuple[str, str, str]:
        """Return (status, msg, hint) aggregated across all entries."""
        if not self.entries:
            return "ok", "", ""
        results = [entry.check() for entry in self.entries]
        statuses = {status for status, _ in results}
        if "error" in statuses:
            status = "error"
        elif "warn" in statuses:
            status = "warn"
        else:
            return "ok", "", ""
        msgs = "; ".join(
            f"{entry.env_var}: {message}"
            for entry, (_, message) in zip(self.entries, results)
            if message
        )
        return status, msgs, ", ".join(self.hints())

    def hints(self) -> list[str]:
        """Return failure_hint if set, else unique non-None hints from all entries."""
        if self.failure_hint:
            return [self.failure_hint]
        seen: set[str] = set()
        result: list[str] = []
        for entry in self.entries:
            if entry.hint and entry.hint not in seen:
                seen.add(entry.hint)
                result.append(entry.hint)
        return result

    def effective_hints(self, override_hints: dict[str, str]) -> list[str]:
        """Return override_hints for matching env vars, falling back to static hints."""
        overrides = [
            override_hints[entry.env_var]
            for entry in self.entries
            if entry.env_var in override_hints
        ]
        return overrides if overrides else self.hints()

    def load(self, base_dir: Path) -> None:
        """Load all entry source files into os.environ."""
        for entry in self.entries:
            entry.load(base_dir)

    def get(self, env_var: str, base_dir: Path = Path(".")) -> str | None:
        """Return the value of env_var via its declared ConfigurationEntry, or None."""
        entry = next(
            (entry for entry in self.entries if entry.env_var == env_var), None
        )
        return entry.value(base_dir) if entry else None
