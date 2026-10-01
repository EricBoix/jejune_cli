"""Single source of truth for all package-relative resource paths."""

from pathlib import Path

_PKG = Path(__file__).parent


class TemplatePaths:
    ROOT = _PKG / "templates"
    ECOSYSTEM_ENV_CONFIG = ROOT / "ecosystem" / "env-config"
    CATALOG_TRIVIAL = ROOT / "catalog" / "trivial-catalog.yaml"
    DEPLOYER_UI = ROOT / "deployer" / "ui-deployment"
    DOC_STEWARD = ROOT / "doc-steward"


class SchemaPaths:
    ROOT = _PKG / "schema"
    CATALOG = ROOT / "catalog.yaml"
    MANIFEST = ROOT / "manifest.yaml"


class CatalogConfig:
    REPO_NAME = "jejune_catalog"
    FULL_CATALOG = "full-catalog.yaml"
    CONFIG_VAR = "JEJUNE_ROOT_DIR"
    PLACEHOLDER = "_CHANGE_ME"
