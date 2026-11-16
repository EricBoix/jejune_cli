"""Detection of jejune editable installs whose source directory has vanished."""

import sysconfig
from pathlib import Path


class StaleEditableInstalls:
    """Finds ``_editable_impl_jejune*.pth`` files pointing to missing directories.

    Python's ``site`` module prints a warning for each such path while the
    interpreter starts, before any jejune code can run. The only thing jejune
    can do is explain those warnings once it is running.
    """

    PTH_GLOB = "_editable_impl_jejune*.pth"

    NOTICE = (
        "Note: the sys.path warnings printed above come from jejune plugin "
        "packages installed from a directory that no longer exists. "
        "They are harmless; run `jejune plugin-packages install` inside the "
        "deployment to fix them."
    )

    def __init__(self, site_packages_dir: Path | None = None) -> None:
        self._site_packages_dir = site_packages_dir or Path(
            sysconfig.get_paths()["purelib"]
        )

    def missing_targets(self) -> list[Path]:
        missing: list[Path] = []
        for pth_file in sorted(self._site_packages_dir.glob(self.PTH_GLOB)):
            for line in pth_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "import ")):
                    continue
                if not Path(line).exists():
                    missing.append(Path(line))
        return missing

    def has_stale(self) -> bool:
        return bool(self.missing_targets())
