"""Cloning or updating the repositories of a catalog in .jejune/tmp."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .component_catalog_document import CatalogDocument
from .component_catalog_file import CatalogFile
from .component_ecosystem import EcosystemDirectories


UpdateStatus = Literal["cloned", "updated", "up-to-date", "skipped", "failed"]


@dataclass(frozen=True)
class UpdateOutcome:
    """What `ecosystem update` did (or could not do) for one repository."""

    name: str
    status: UpdateStatus
    message: str = ""


class CatalogUpdater:
    """Brings the repositories of the entries of a catalog up to date."""

    def __init__(self, ecosystem, git_access) -> None:
        self._ecosystem = ecosystem
        self._git_access = git_access

    def update_catalog_repos(
        self, catalog_path: Path, deploy_dir: Path | None = None
    ) -> list[UpdateOutcome]:
        """Clone (when missing) or update, in .jejune/tmp/, every entry of the catalog.

        A failing entry (malformed, unusable git-access configuration, git error)
        yields a `failed` outcome carrying the reason: the other entries are
        still processed.
        """
        try:
            raw_documents = CatalogFile(catalog_path).raw_documents()
        except ValueError as exc:
            return [UpdateOutcome(str(catalog_path), "failed", str(exc))]
        directories = self._ecosystem.resolve_dirs(deploy_dir)
        outcomes: list[UpdateOutcome] = []
        for index, raw_document in enumerate(raw_documents, 1):
            document = CatalogDocument.from_mapping(raw_document)
            if document is None:
                outcomes.append(
                    UpdateOutcome(
                        f"entry #{index}",
                        "failed",
                        "catalog entry without a `name` or a `url`",
                    )
                )
                continue
            outcomes.append(
                self.update_catalog_entry(document, directories, deploy_dir)
            )
        return outcomes

    def update_catalog_entry(
        self,
        entry: CatalogDocument,
        directories: EcosystemDirectories,
        deploy_dir: Path | None = None,
    ) -> UpdateOutcome:
        location = self._ecosystem.locate(entry.name, directories)
        if location.tier == "root":
            return UpdateOutcome(
                entry.name,
                "skipped",
                "found in JEJUNE_ROOT_DIR: update it with git there",
            )
        try:
            entry.resolve_credentials(self._git_access)
        except ValueError as exc:
            return UpdateOutcome(entry.name, "failed", f"git-access: {exc}")
        token_file = entry.effective_token_file
        try:
            if location.tier == "tmp":
                was_updated = self._ecosystem.update_tmp_repo(location.local_path, token_file)
                return UpdateOutcome(
                    entry.name, "updated" if was_updated else "up-to-date"
                )
            self._ecosystem.clone_into_tmp(entry.name, entry.url, token_file, deploy_dir)
            return UpdateOutcome(entry.name, "cloned")
        except subprocess.CalledProcessError as exc:
            return UpdateOutcome(
                entry.name,
                "failed",
                f"git exited with status {exc.returncode}: check the `url` of the "
                f"entry ({entry.url}) and its access key "
                "(`jejune git-access check-config`)",
            )
