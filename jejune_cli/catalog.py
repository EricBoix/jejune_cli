import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
import yaml

from ._env import dot_jejune  # noqa: F401 — re-exported for jejune_catalog plugin
from .convert import convert_configured as _convert_configured, image_built as _convert_image_built
from .neo4j import container_running as _neo4j_running
from .test import _check_doc_yaml, _tmp_dir

_TEMPLATES = Path(__file__).parent / "templates"
_TRIVIAL_CATALOG = _TEMPLATES / "catalog-curator" / "trivial-catalog.yaml"


@click.group(short_help="Catalog utilities")
def catalog():
    """Catalog utilities for catalog-curator workspaces."""


@catalog.command("test")
@click.argument("catalog_file", required=False, default=None)
@click.option(
    "--root-dir",
    envvar="JEJUNE_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding side-by-side jejune_* clones (default: $JEJUNE_ROOT_DIR).",
)
@click.option(
    "--repo",
    default=None,
    help="Operate on this repository only (by name).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print referenced files for each document.",
)
def catalog_test(catalog_file, root_dir, repo, verbose):
    """Validate jejune_doc_* repositories found in the catalog.

    CATALOG_FILE defaults to $JEJUNE_CATALOG, then .jejune/catalog.yaml.

    Repositories are expected under ROOT_DIR/<name>/. Missing repositories
    (or all when ROOT_DIR is unset) are cloned into .jejune/tmp/ which is
    gitignored automatically.

    For each repository, doc.yaml is parsed and every file it references is
    checked for existence. Exits with a non-zero status if any check fails.
    """
    if catalog_file is None:
        catalog_file = os.environ.get("JEJUNE_CATALOG")
    if catalog_file is None:
        default = dot_jejune() / "catalog.yaml"
        if not default.exists():
            raise click.ClickException(
                "No catalog specified. Set $JEJUNE_CATALOG, pass CATALOG_FILE, "
                "or run `jejune configure init` to create .jejune/catalog.yaml."
            )
        catalog_file = str(default)

    root = Path(root_dir) if root_dir else None
    if root is not None and not root.exists():
        source = (
            "$JEJUNE_ROOT_DIR"
            if os.environ.get("JEJUNE_ROOT_DIR") == root_dir
            else "--root-dir"
        )
        raise click.ClickException(f"ROOT_DIR ({source}) does not exist: {root}")

    catalog_path = Path(catalog_file)
    if not catalog_path.exists():
        raise click.ClickException(f"Catalog file not found: {catalog_file}")
    docs = yaml.safe_load(catalog_path.read_text())["documents"]

    if repo:
        docs = [d for d in docs if d["name"] == repo]
        if not docs:
            raise click.ClickException(f"Repository '{repo}' not found in catalog.")

    tmp: Path | None = None
    all_ok = True

    for doc in docs:
        name = doc["name"]
        url = doc["url"]

        repo_dir = root / name if root is not None else None
        if repo_dir is None or not repo_dir.exists():
            if tmp is None:
                tmp = _tmp_dir()
            repo_dir = tmp / name
            if not repo_dir.exists():
                click.echo(f"Cloning {name} ...")
                subprocess.run(["git", "clone", url, str(repo_dir)], check=True)

        cloned_label = click.style("cloned", fg="green")
        errors, file_refs = _check_doc_yaml(repo_dir)
        if errors:
            all_ok = False
            doc_label = click.style("invalid", fg="red")
            click.echo(f"  {name:<40}  {cloned_label} / {doc_label}")
            if verbose:
                for err in errors:
                    click.echo(f"      {click.style(err, fg='red')}")
        else:
            doc_label = click.style("valid", fg="green")
            click.echo(f"  {name:<40}  {cloned_label} / {doc_label}")
            if verbose:
                key_width = max((len(k) for k, _ in file_refs), default=0)
                for key, rel in file_refs:
                    click.echo(f"      {key:<{key_width}}  {rel}")

    click.echo()
    if all_ok:
        click.echo(click.style(f"{len(docs)} repo(s) — all ok.", fg="green"))
    else:
        click.echo(click.style(f"{len(docs)} repo(s) — some checks failed.", fg="red"))
        sys.exit(1)


@catalog.command("sample")
def catalog_sample():
    """Copy the built-in catalog template to catalog.yaml in the current directory."""
    target = Path.cwd() / "catalog.yaml"
    if target.exists():
        click.echo(
            click.style(
                f"Warning: {target} already exists — not overwriting.",
                fg="yellow",
            ),
            err=True,
        )
        return
    shutil.copy(_TRIVIAL_CATALOG, target)
    click.echo(f"Created {target}")


# ---------------------------------------------------------------------------
# Catalog configuration status (used by the jejune_catalog plugin)
# ---------------------------------------------------------------------------

_PLACEHOLDER = "_CHANGE_ME"


def _catalog_config_status() -> tuple[str, str]:
    """Return (status, raw_msg) for catalog configuration."""
    val = os.environ.get("JEJUNE_ROOT_DIR")
    root_valid = bool(val) and _PLACEHOLDER not in val
    cat_exists = (dot_jejune() / "catalog.yaml").exists()
    if not root_valid and not cat_exists:
        msg = (
            "JEJUNE_ROOT_DIR not configured; catalog.yaml missing"
            if not val else
            "JEJUNE_ROOT_DIR has placeholder value; catalog.yaml missing"
        )
        return "error", msg
    if not root_valid:
        if not val:
            return "warn", "JEJUNE_ROOT_DIR not configured"
        return "error", "JEJUNE_ROOT_DIR has placeholder value"
    if not cat_exists:
        return "error", "catalog.yaml missing"
    return "ok", ""


# ---------------------------------------------------------------------------
# Internal helpers (imported by the jejune_catalog plugin)
# ---------------------------------------------------------------------------

def _gh_is_private(slug: str) -> tuple[bool | None, str]:
    """Query GitHub via gh CLI; return (is_private, error_message)."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", slug, "--json", "isPrivate", "--jq", ".isPrivate"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        return None, "gh CLI not found"
    except subprocess.TimeoutExpired:
        return None, "gh query timed out"
    if result.returncode != 0:
        return None, result.stderr.strip() or "gh query failed"
    return result.stdout.strip() == "true", ""


def _check_catalog_impl(catalog: Path, root_dir: Path | None) -> list[tuple[str, bool, str]]:
    """Check each catalog entry for visibility and local clone; return (name, ok, message)."""
    if not catalog.exists():
        return [("catalog.yaml", False, f"not found: {catalog}")]
    docs = yaml.safe_load(catalog.read_text()).get("documents", [])
    results: list[tuple[str, bool, str]] = []
    for doc in docs:
        name = doc["name"]
        url = doc["url"].rstrip("/")
        expected_public = doc.get("public", True)
        issues: list[str] = []

        if root_dir is None:
            issues.append("JEJUNE_ROOT_DIR not set")
        elif not (root_dir / name).is_dir():
            issues.append(f"not cloned under {root_dir}")

        parts = url.split("/")
        if len(parts) >= 2:
            slug = f"{parts[-2]}/{parts[-1]}"
            is_private, err = _gh_is_private(slug)
            if err:
                issues.append(err)
            else:
                actual_public = not is_private
                if actual_public != expected_public:
                    catalog_val = "public" if expected_public else "private"
                    github_val = "public" if actual_public else "private"
                    issues.append(
                        f"visibility mismatch: catalog={catalog_val}, GitHub={github_val}"
                    )

        results.append((name, not issues, "; ".join(issues) if issues else "ok"))
    return results


def _check_deployment_impl(
    deployment_path: Path,
    catalog_ref: Path,
    root_dir: Path | None,
) -> list[tuple[str, bool, str]]:
    """Validate a deployment directory; return (item, ok, message)."""
    results: list[tuple[str, bool, str]] = []

    for fname in ("catalog.yaml", "deployment.env"):
        f = deployment_path / fname
        results.append((fname, f.exists(), "ok" if f.exists() else "missing"))

    catalog_path = deployment_path / "catalog.yaml"
    if not catalog_path.exists():
        return results

    ref_docs: dict[str, dict] = {}
    if catalog_ref.exists():
        for doc in yaml.safe_load(catalog_ref.read_text()).get("documents", []):
            ref_docs[doc["name"]] = doc

    for doc in yaml.safe_load(catalog_path.read_text()).get("documents", []):
        name = doc["name"]
        url = doc["url"].rstrip("/")
        issues: list[str] = []

        if root_dir is None:
            issues.append("JEJUNE_ROOT_DIR not set")
        elif not (root_dir / name).is_dir():
            issues.append(f"not cloned under {root_dir}")

        if name in ref_docs:
            ref_url = ref_docs[name]["url"].rstrip("/")
            if url != ref_url:
                issues.append(f"URL drift: deployment={url!r}, reference={ref_url!r}")

        label = "public" if doc.get("public") else "private"
        results.append((
            name,
            not issues,
            f"ok ({label})" if not issues else "; ".join(issues),
        ))

    return results


def _sync_catalog_impl(
    catalog: Path,
    root_dir: Path,
    do_add: bool,
) -> list[tuple[str, bool, str]]:
    """Scan JEJUNE_ROOT_DIR for jejune_doc_* repos and compare against catalog."""
    import click
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
            capture_output=True, text=True,
        )
        if remote.returncode != 0:
            results.append((name, False, "no git remote"))
            continue

        url = remote.stdout.strip().removesuffix(".git")
        parts = url.split("/")
        slug = f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else ""

        if not slug:
            results.append((name, False, f"unexpected remote URL: {url}"))
            continue

        is_private, err = _gh_is_private(slug)
        if err:
            results.append((name, False, err))
        elif is_private:
            results.append((name, True, "private — add manually to deployment catalog if needed"))
        else:
            results.append((name, False, "public repo missing from catalog"))
            to_add.append((name, url))

    if do_add and to_add and catalog.exists():
        with catalog.open("a") as f:
            for name, url in to_add:
                f.write(f"  - name: {name}\n")
                f.write(f"    url: {url}\n")
                f.write(f"    public: true\n")
        click.echo(f"Added {len(to_add)} repo(s) to {catalog}.")

    return results


# ---------------------------------------------------------------------------
# Called by `jejune doctor`
# ---------------------------------------------------------------------------

def run_all(
    components: set[str] | None = None,
) -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
]:
    """Return (config_results, avail_results) for jejune doctor.

    Each entry is (component, status, message).
    When *components* is given, only those components are checked.
    """
    from .configuration import CONFIG_GROUPS, check_config_group
    from .plugin import _REGISTRY

    config: list[tuple[str, str, str]] = []
    avail:  list[tuple[str, str, str]] = []

    def _visible(name: str) -> bool:
        return components is None or name in components

    for group, (keys, _) in CONFIG_GROUPS.items():
        if not _visible(group):
            continue
        status, msg = check_config_group(keys)
        config.append((group, status, msg))

    # llm-observability config is now in CONFIG_GROUPS and handled by the loop above

    if _visible("neo4j"):
        running, msg = _neo4j_running()
        avail.append(("neo4j", "ok" if running else "warn", msg))

    if _visible("llm"):
        from .llm import llm_check_availability as _llm_check
        ok, msg = _llm_check()
        status = "ok" if ok else ("warn" if msg == "not configured" else "error")
        avail.append(("llm", status, msg))

    if _visible("llm-observability"):
        from .llm_observability import llm_observability_available as _lo_available
        ok, msg = _lo_available()
        avail.append(("llm-observability", "ok" if ok else "warn", msg))

    if _visible("graph"):
        from .graph import graph_available as _graph_available
        ok, msg = _graph_available()
        avail.append(("graph", "ok" if ok else "error", msg))

    if _visible("convert") and _convert_configured():
        built, msg = _convert_image_built()
        avail.append(("convert", "ok" if built else "warn", msg))

    for plugin in _REGISTRY:
        if not _visible(plugin.name):
            continue
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return config, avail
