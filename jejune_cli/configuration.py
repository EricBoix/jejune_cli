"""configuration: aggregate container for ConfigurationEntry instances."""

from pathlib import Path

from .configuration_entry import ConfigurationEntry


class Configuration:
    def __init__(self, *entries: ConfigurationEntry) -> None:
        self.entries: list[ConfigurationEntry] = list(entries)

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def check(self) -> tuple[str, str, str]:
        """Return (status, msg, hint) aggregated across all entries."""
        if not self.entries:
            return "ok", "", ""
        results = [e.check() for e in self.entries]
        statuses = {s for s, _ in results}
        if "error" in statuses:
            status = "error"
        elif "warn" in statuses:
            status = "warn"
        else:
            return "ok", "", ""
        msgs = "; ".join(
            f"{e.env_var}: {m}" for e, (_, m) in zip(self.entries, results) if m
        )
        return status, msgs, ", ".join(self.hints())

    def hints(self) -> list[str]:
        """Return unique non-None hints from all entries."""
        seen: set[str] = set()
        result: list[str] = []
        for e in self.entries:
            if e.hint and e.hint not in seen:
                seen.add(e.hint)
                result.append(e.hint)
        return result

    def effective_hints(self, override_hints: dict[str, str]) -> list[str]:
        """Return override_hints for matching env vars, falling back to static hints."""
        overrides = [
            override_hints[e.env_var]
            for e in self.entries
            if e.env_var in override_hints
        ]
        return overrides if overrides else self.hints()

    def entries_check(self) -> list[tuple[str, str]]:
        """Return (env_var, status) for each entry; status is 'ok', 'missing', or 'placeholder'."""
        return [(e.env_var, e.check()[1] or "ok") for e in self.entries]

    def load(self, base_dir: Path) -> None:
        """Load all entry source files into os.environ."""
        for e in self.entries:
            e.load(base_dir)

    def get(self, env_var: str, base_dir: Path = Path(".")) -> str | None:
        """Return the value of env_var via its declared ConfigurationEntry, or None."""
        entry = next((e for e in self.entries if e.env_var == env_var), None)
        return entry.value(base_dir) if entry else None
