"""Manifest configuration component."""

from pathlib import Path
from typing import ClassVar
import yaml

from .component_with_config import ConfComp


class comp_manifest(ConfComp):
    _SCHEMA_PATH: ClassVar[Path] = Path(__file__).parent / "schema" / "manifest.yaml"

    def __init__(self, doc_repository_directory: Path = Path.cwd()) -> None:
        super().__init__(name="manifest")
        self.cli_name = self.name
        self.doc_repository_directory = doc_repository_directory

    def _load_doc_schema(self) -> tuple[dict, dict] | None:
        doc_yaml = self.doc_repository_directory / "manifest.yaml"
        if not doc_yaml.exists():
            return None
        schema = yaml.safe_load(self._SCHEMA_PATH.read_text())
        data = yaml.safe_load(doc_yaml.read_text()) or {}
        return schema, data

    def _check_graph_extractions_entries(self, schema: dict, data: dict) -> list[str]:
        """Validate each entry in graph_extractions against the per-entry schema fields."""
        entry_required = schema.get("graph_extractions_entry_required_fields", [])
        entry_optional = schema.get("graph_extractions_entry_optional_fields", [])
        entry_known = set(entry_required) | set(entry_optional)
        errors = []
        for index, entry in enumerate(data.get("graph_extractions") or []):
            for field_name in entry_required:
                if field_name not in entry:
                    errors.append(
                        f"graph_extractions[{index}]: required field '{field_name}' missing"
                    )
            unknown_entry_fields = [key for key in entry if key not in entry_known]
            if unknown_entry_fields:
                errors.append(
                    f"graph_extractions[{index}]: unknown field(s): {', '.join(unknown_entry_fields)}"
                )
        return errors

    def check_manifest_referenced_files(
        self,
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Comprehensive diagnostic of manifest.yaml: structural validation plus file-reference checks.

        Delegates structural validation to check_manifest_against_schema(), then checks that every
        file-field value resolves to an existing path under doc_repository_directory.
        Returns (errors, file_refs) where file_refs lists (field_name, relative_path)
        for every file field present in the manifest, regardless of existence.
        """
        cfg_status, cfg_msg = self.check_manifest_against_schema()
        if cfg_status == "error" and cfg_msg == "manifest.yaml missing":
            return [
                f"manifest.yaml missing (see {self._SCHEMA_PATH} for the expected format)"
            ], []
        errors: list[str] = [] if cfg_status == "ok" else [cfg_msg]
        file_refs: list[tuple[str, str]] = []

        schema, data = self._load_doc_schema()

        for field_name in schema.get("file_fields", []):
            relative_path = data.get(field_name)
            if relative_path is None:
                continue
            file_refs.append((field_name, relative_path))
            if not (self.doc_repository_directory / relative_path).exists():
                errors.append(f"{field_name}: {relative_path!r} not found")

        entry_file_fields = schema.get("graph_extractions_entry_file_fields", [])
        for index, entry in enumerate(data.get("graph_extractions") or []):
            for field_name in entry_file_fields:
                relative_path = entry.get(field_name)
                if relative_path is None:
                    continue
                label = f"graph_extractions[{index}].{field_name}"
                file_refs.append((label, relative_path))
                if not (self.doc_repository_directory / relative_path).exists():
                    errors.append(f"{label}: {relative_path!r} not found")

        if errors:
            errors.append(f"see {self._SCHEMA_PATH} for the expected format")
        return errors, file_refs

    def check_manifest_against_schema(self) -> tuple[str, str]:
        """Structural validation of manifest.yaml against the schema.

        Returns "error" when the file is absent or required fields are missing,
        "warn" for unknown fields, "ok" otherwise.
        """
        loaded = self._load_doc_schema()
        if loaded is None:
            return "error", "manifest.yaml missing"
        schema, data = loaded
        missing = [
            field_name
            for field_name in schema.get("required_fields", {})
            if field_name not in data
        ]
        missing += [
            field_name
            for field_name in schema.get("required_file_fields", [])
            if field_name not in data
        ]
        if missing:
            return "error", f"required field(s) missing: {', '.join(missing)}"
        known_keys = (
            set(schema.get("required_fields", {}).keys())
            | set(schema.get("optional_fields", {}).keys())
            | set(schema.get("file_fields", []))
        )
        unknown = [field_name for field_name in data if field_name not in known_keys]
        if unknown:
            return "warn", f"unknown field(s): {', '.join(unknown)}"
        entry_errors = self._check_graph_extractions_entries(schema, data)
        if entry_errors:
            return "error", entry_errors[0]
        return "ok", ""

    def check_availability(self) -> tuple[str, str]:
        """File-existence check for all file fields declared in manifest.yaml.

        Returns "warn" when the file is absent, "error" when declared file-field
        paths do not exist on disk, "ok" otherwise.
        """
        errors, _ = self.check_manifest_referenced_files()
        if not errors:
            return "ok", ""
        if errors[0].startswith("manifest.yaml missing"):
            return "warn", "manifest.yaml missing"
        return "error", errors[0]

    def check_config(self) -> tuple[str, str]:
        return self.check_manifest_against_schema()

    def check(self) -> tuple[str, str]:
        return self.check_availability()
