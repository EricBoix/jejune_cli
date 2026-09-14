"""configuration: aggregate container for configuration_entry instances."""

from pathlib import Path

from .configuration_entry import configuration_entry


class configuration:
    def __init__(self, *entries: configuration_entry) -> None:
        self.configuration: list[configuration_entry] = list(entries)

    def __bool__(self) -> bool:
        return bool(self.configuration)

    def __iter__(self):
        return iter(self.configuration)

    def check(self) -> tuple[str, str, str]:
        """Return (status, msg, hint) aggregated across all entries."""
        if not self.configuration:
            return "ok", "", ""
        results = [e.check() for e in self.configuration]
        statuses = {s for s, _ in results}
        if "error" in statuses:
            status = "error"
        elif "warn" in statuses:
            status = "warn"
        else:
            return "ok", "", ""
        msgs = "; ".join(
            f"{e.env_var}: {m}"
            for e, (_, m) in zip(self.configuration, results)
            if m
        )
        return status, msgs, ", ".join(self.hints())

    def hints(self) -> list[str]:
        """Return unique non-None hints from all entries."""
        seen: set[str] = set()
        result: list[str] = []
        for e in self.configuration:
            if e.hint and e.hint not in seen:
                seen.add(e.hint)
                result.append(e.hint)
        return result

    def effective_hints(self, override_hints: dict[str, str]) -> list[str]:
        """Return override_hints for matching env vars, falling back to static hints."""
        overrides = [
            override_hints[e.env_var]
            for e in self.configuration
            if e.env_var in override_hints
        ]
        return overrides if overrides else self.hints()

    def load(self, base_dir: Path) -> None:
        """Load all entry source files into os.environ."""
        for e in self.configuration:
            e.load(base_dir)
