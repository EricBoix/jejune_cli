"""dot_jejune: encapsulates the .jejune/ workspace directory."""
from pathlib import Path
from typing import ClassVar


class dot_jejune:
    _DOT_JEJUNE: ClassVar[str] = ".jejune"
    _TMP_PATTERN: ClassVar[str] = str(Path(_DOT_JEJUNE) / "tmp") + "/"

    def __init__(self, cwd: Path = Path.cwd()) -> None:
        self._cwd = cwd
        self._path = self._cwd / self._DOT_JEJUNE

    def __truediv__(self, other) -> Path:
        return self._path / other

    def is_dir(self) -> bool:
        return self._path.is_dir()

    def _ensure_gitignored(self) -> None:
        gitignore = self._cwd / ".gitignore"
        if gitignore.exists():
            if any(line.strip() == self._TMP_PATTERN for line in gitignore.read_text().splitlines()):
                return
            with gitignore.open("a") as file_handle:
                file_handle.write(f"{self._TMP_PATTERN}\n")
        else:
            gitignore.write_text(f"{self._TMP_PATTERN}\n")

    def tmp_dir(self) -> Path:
        """Return (and create) the .jejune/tmp/ scratch directory, ensuring it is gitignored."""
        tmp = self._path / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        self._ensure_gitignored()
        return tmp
