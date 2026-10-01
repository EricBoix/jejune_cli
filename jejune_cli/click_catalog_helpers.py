"""Schema validation, git probing, catalog operations, and converter utilities for click_catalog."""

import os
import subprocess
from pathlib import Path

import click
import yaml

from ._package_paths import CatalogConfig, SchemaPaths
from .dot_jejune import DotJejune


def load_catalog_docs(catalog_file: str | None) -> list[dict]:
    """Load and return the documents list from a catalog YAML file."""
    if catalog_file is None:
        catalog_file = os.environ.get("JEJUNE_CATALOG") or str(
            Path.cwd() / "catalog.yaml"
        )
    p = Path(catalog_file)
    if not p.exists():
        raise click.ClickException(f"Catalog file not found: {catalog_file}")
    return yaml.safe_load(p.read_text())["documents"]


def catalog_config_status() -> tuple[str, str]:
    """Return (status, raw_msg) for catalog configuration."""
    val = os.environ.get(CatalogConfig.CONFIG_VAR)
    if not val:
        return "warn", f"{CatalogConfig.CONFIG_VAR} not configured"
    if CatalogConfig.PLACEHOLDER in val:
        return "warn", f"{CatalogConfig.CONFIG_VAR} has placeholder value"
    return "ok", ""


def validate_catalog_entry(doc: object, index: int) -> list[str]:
    """Validate one entry against the deployment catalog schema; return error strings."""
    if not isinstance(doc, dict):
        return [f"entry #{index}: not a mapping"]
    schema = yaml.safe_load(SchemaPaths.CATALOG.read_text())
    errors: list[str] = []
    _TYPE_MAP = {"string": str, "boolean": bool}
    for field, ftype in schema.get("required_fields", {}).items():
        if field not in doc:
            errors.append(f"required field '{field}' missing")
        elif not isinstance(doc[field], _TYPE_MAP.get(ftype, object)):
            errors.append(f"'{field}' must be a {ftype}")
    for field, ftype in schema.get("optional_fields", {}).items():
        if field in doc and not isinstance(doc[field], _TYPE_MAP.get(ftype, object)):
            errors.append(f"'{field}' must be a {ftype}")
    if errors:
        errors.append(f"see {SchemaPaths.CATALOG} for the expected format")
    return errors


def _git_is_private(url: str) -> tuple[bool | None, str]:
    """Probe a remote URL via git ls-remote; return (is_private, error_message).

    Returns (False, "") when the remote is reachable (public or authenticated).
    Returns (True, "") when git exits 128, which indicates the remote refused
    anonymous access (error code 128: repository not found or access denied).
    Returns (None, msg) for transient or unrecognized failures.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "--heads", url],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        return None, "git not found"
    except subprocess.TimeoutExpired:
        return None, "git ls-remote timed out"
    if result.returncode == 0 or result.returncode == 2:
        # 0 = refs found; 2 = no refs (empty repo) — both mean reachable
        return False, ""
    if result.returncode == 128:
        return True, ""
    return None, f"git ls-remote exited {result.returncode}: {result.stderr.strip()}"


def check_catalog(catalog: Path, root_dir: Path | None) -> list[tuple[str, bool, str]]:
    """Check each catalog entry for visibility and local clone; return (name, ok, message)."""
    if not catalog.exists():
        return [("catalog.yaml", False, f"not found: {catalog}")]
    docs = yaml.safe_load(catalog.read_text()).get("documents", [])
    results: list[tuple[str, bool, str]] = []
    for i, doc in enumerate(docs):
        schema_errors = validate_catalog_entry(doc, i)
        if schema_errors:
            label = doc.get("name") if isinstance(doc, dict) else None
            results.append((label or f"entry #{i}", False, "; ".join(schema_errors)))
            continue
        name = doc["name"]
        url = doc["url"].rstrip("/")
        expected_public = doc.get("public", True)
        issues: list[str] = []

        if root_dir is None:
            issues.append("JEJUNE_ROOT_DIR not set")
        elif not (root_dir / name).is_dir():
            issues.append(f"not cloned under {root_dir}")

        is_private, err = _git_is_private(url)
        if err:
            issues.append(err)
        else:
            actual_public = not is_private
            if actual_public != expected_public:
                catalog_val = "public" if expected_public else "private"
                remote_val = "public" if actual_public else "private"
                issues.append(
                    f"visibility mismatch: catalog={catalog_val}, remote={remote_val}"
                )

        results.append((name, not issues, "; ".join(issues) if issues else "ok"))
    return results


def sync_catalog(
    catalog: Path,
    root_dir: Path,
    do_add: bool,
) -> tuple[list[tuple[str, bool, str]], int]:
    """Scan JEJUNE_ROOT_DIR for jejune_doc_* repos and compare against catalog.

    Returns (results, n_added) where n_added is the count of repos appended to
    catalog when do_add is True.
    """
    existing: set[str] = set()
    if catalog.exists():
        for doc in yaml.safe_load(catalog.read_text()).get("documents", []):
            existing.add(doc["name"])

    results: list[tuple[str, bool, str]] = []
    to_add: list[tuple[str, str]] = []

    for repo_dir in sorted(root_dir.glob("jejune_doc_*")):
        if not repo_dir.is_dir():
            continue
        name = repo_dir.name

        if name in existing:
            results.append((name, True, "already in catalog"))
            continue

        remote = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if remote.returncode != 0:
            results.append((name, False, "no git remote"))
            continue

        url = remote.stdout.strip().removesuffix(".git")

        is_private, err = _git_is_private(url)
        if err:
            results.append((name, False, err))
            continue
        elif is_private:
            results.append(
                (name, True, "private — add manually to deployment catalog if needed")
            )
        else:
            results.append((name, False, "public repo missing from catalog"))
            to_add.append((name, url))

    n_added = 0
    if do_add and to_add and catalog.exists():
        with catalog.open("a") as fh:
            for name, url in to_add:
                fh.write(f"  - name: {name}\n")
                fh.write(f"    url: {url}\n")
                fh.write(f"    public: true\n")
        n_added = len(to_add)

    return results, n_added


def iter_docs(docs, root, eco_tmp, ecosystem):
    """Yield (name, url, repo_dir) for each catalog entry.

    Resolution order: JEJUNE_ROOT_DIR → .jejune/tmp → clone into .jejune/tmp.
    """
    tmp = None
    for doc in docs:
        name, url = doc["name"], doc["url"]
        tier, base = ecosystem.repo_status(name, root, eco_tmp)
        if tier in ("root", "tmp"):
            repo_dir = Path(base)
        else:
            if tmp is None:
                tmp = DotJejune().tmp_dir()
            repo_dir = tmp / name
            if not repo_dir.exists():
                print(f"Cloning {name} ...")
                subprocess.run(["git", "clone", url, str(repo_dir)], check=True)
        yield name, url, repo_dir


# ---------------------------------------------------------------------------
# Per-document converter build and test logic
# ---------------------------------------------------------------------------

_DOC_PREFIX = "jejune_doc_"


def _docker_image_name(repo_dir: Path) -> str:
    name = repo_dir.resolve().name
    if name.startswith(_DOC_PREFIX):
        name = name[len(_DOC_PREFIX) :]
    return f"jejune:convert_{name}" if name else "jejune:convert"


def _has_converter(repo_dir: Path) -> tuple[bool, Path, Path]:
    """Return (has_converter, dockerfile, context)."""
    ctx = repo_dir / "DockerContext"
    df = ctx / "Dockerfile"
    return (ctx.is_dir() and df.exists()), df, ctx


def convert_test_doc(repo_dir: Path, no_cache: bool, no_build: bool) -> tuple[str, str]:
    """Return (outcome, detail). outcome ∈ {skipped, build_failed, unchanged, changed}."""
    has, dockerfile, context = _has_converter(repo_dir)
    if not has:
        return "skipped", "no DockerContext"
    image = _docker_image_name(repo_dir)
    if not no_build:
        extra = ["--no-cache"] if no_cache else []
        result = subprocess.run(
            [
                "docker",
                "build",
                *extra,
                "-t",
                image,
                "-f",
                str(dockerfile),
                str(context),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()
            return "build_failed", tail[-1] if tail else "build failed"
    else:
        result = subprocess.run(
            ["docker", "images", "-q", image], capture_output=True, text=True
        )
        if not (result.returncode == 0 and result.stdout.strip()):
            return "build_failed", f"image {image!r} not found"
    result = subprocess.run(
        ["docker", "run", "--rm", image, "--test"], capture_output=True, text=True
    )
    return (
        ("unchanged", "tests passed")
        if result.returncode == 0
        else ("changed", "tests failed")
    )
