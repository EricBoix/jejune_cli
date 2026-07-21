import os
import subprocess
from pathlib import Path

import click
import yaml

from ._env import dot_jejune
from .configuration import (
    CONFIG_GROUPS, _catalog_config_status, check_config_group,
    component_config_check, print_config_hint, print_config_status,
)
from .llm import (
    DEFAULT_INFERENCE_PATH as _LLM_DEFAULT_INFERENCE_PATH,
    infer_server_url as _infer_llm_server_url,
    check_server as _check_llm_server,
    check_auth as _check_llm_auth,
    check_model as _check_llm_model,
    check_inference_endpoint as _check_llm_inference_endpoint,
    check_inference as _check_llm_inference,
)
from .llm_observability import container_running as _llm_obs_running
from .neo4j import container_running as _neo4j_running


# ---------------------------------------------------------------------------
# Internal helpers
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
            issues.append("JJ_ROOT_DIR not set")
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
            issues.append("JJ_ROOT_DIR not set")
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
    """Scan JJ_ROOT_DIR for jj_doc_* repos and compare against catalog."""
    existing: set[str] = set()
    if catalog.exists():
        for doc in yaml.safe_load(catalog.read_text()).get("documents", []):
            existing.add(doc["name"])

    results: list[tuple[str, bool, str]] = []
    to_add: list[tuple[str, str]] = []

    for repo_dir in sorted(root_dir.glob("jj_doc_*")):
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
# Click commands
# ---------------------------------------------------------------------------

@click.group()
def catalog():
    """Manage the catalog of jj_doc_* repositories (collection-level)."""


@catalog.command("check-config")
def check_config():
    """Check whether the catalog component is properly configured."""
    print_config_status("catalog")


@catalog.command("hint-config")
def hint_config():
    """Show the configuration hint for the catalog component."""
    print_config_hint("catalog")


@catalog.command("check")
@click.option(
    "--catalog", "catalog_path",
    default=None,
    type=click.Path(),
    help="Path to catalog.yaml (default: .jejune/catalog.yaml).",
)
@click.option(
    "--root-dir",
    envvar="JJ_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding jj_* clones (default: $JJ_ROOT_DIR).",
)
def check(catalog_path, root_dir):
    """Verify catalog.yaml against GitHub visibility and local clones.

    For each entry: confirms the public flag matches actual GitHub visibility
    and that a local clone exists under JJ_ROOT_DIR.
    Requires the gh CLI to be authenticated.
    """
    cfg_status, hint = component_config_check("catalog")
    if cfg_status == "error":
        raise click.ClickException(f"not configured — {hint}")

    cat_path = Path(catalog_path) if catalog_path else dot_jejune() / "catalog.yaml"
    root = Path(root_dir) if root_dir else None
    results = _check_catalog_impl(cat_path, root)

    all_ok = True
    for name, ok, msg in results:
        status = click.style("ok", fg="green") if ok else click.style(msg, fg="red")
        click.echo(f"  {name:<45} {status}")
        if not ok:
            all_ok = False

    if not all_ok:
        raise SystemExit(1)


@catalog.command("sync")
@click.option(
    "--catalog", "catalog_path",
    default=None,
    type=click.Path(),
    help="Path to catalog.yaml (default: .jejune/catalog.yaml).",
)
@click.option(
    "--root-dir",
    envvar="JJ_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding jj_* clones (default: $JJ_ROOT_DIR).",
)
@click.option(
    "--add",
    "do_add",
    is_flag=True,
    default=False,
    help="Append missing public repos to catalog.yaml.",
)
def sync(catalog_path, root_dir, do_add):
    """Report public jj_doc_* repos under JJ_ROOT_DIR missing from catalog.yaml.

    With --add, appends missing public repos to the catalog file in place.
    Private repos are flagged as informational only.
    """
    if not root_dir:
        raise click.ClickException("JJ_ROOT_DIR is not set. Use --root-dir or set the env var.")

    cat_path = Path(catalog_path) if catalog_path else dot_jejune() / "catalog.yaml"
    results = _sync_catalog_impl(cat_path, Path(root_dir), do_add)

    for name, ok, msg in results:
        if ok:
            status = click.style(msg, fg="green")
        else:
            status = click.style(msg, fg="yellow" if "private" in msg else "red")
        click.echo(f"  {name:<45} {status}")


@catalog.command("check-deployment")
@click.argument("deployment_path", type=click.Path(exists=True))
@click.option(
    "--root-dir",
    envvar="JJ_ROOT_DIR",
    default=None,
    type=click.Path(),
    help="Directory holding jj_* clones (default: $JJ_ROOT_DIR).",
)
def check_deployment(deployment_path, root_dir):
    """Validate a deployment directory against catalog.yaml.

    DEPLOYMENT_PATH is the path to a jj_deployments/deploy_*/ directory.
    Checks required files, URL consistency with the reference catalog,
    and local clone presence for each listed repository.
    """
    dep_path = Path(deployment_path)
    root = Path(root_dir) if root_dir else None
    results = _check_deployment_impl(dep_path, dot_jejune() / "catalog.yaml", root)

    all_ok = True
    for item, ok, msg in results:
        status = click.style(msg, fg="green") if ok else click.style(msg, fg="red")
        click.echo(f"  {item:<45} {status}")
        if not ok:
            all_ok = False

    if not all_ok:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Called by `jejune doctor`
# ---------------------------------------------------------------------------

def run_all() -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
]:
    """Return (config_results, avail_results) for jejune doctor.

    Each entry is (component, status, message).
    status: "ok", "warn" (not configured / skipped), "error".

    config_results — was the component configured by the user?
    avail_results  — is the component's service reachable?
    """
    config: list[tuple[str, str, str]] = []
    avail:  list[tuple[str, str, str]] = []
    d = dot_jejune()

    for group, (keys, _) in CONFIG_GROUPS.items():
        status, msg = check_config_group(keys)
        config.append((group, status, msg))

    lo_status, _ = component_config_check("llm-observability")
    config.append(("llm-observability", lo_status, "ok" if lo_status == "ok" else "not configured"))

    cat_status, cat_msg = _catalog_config_status()
    if cat_status != "ok":
        config.append(("catalog", cat_status, cat_msg))
    else:
        cat_results = _check_catalog_impl(d / "catalog.yaml", Path(os.environ["JJ_ROOT_DIR"]))
        failed_repos = [n for n, ok, _ in cat_results if not ok]
        config.append((
            "catalog",
            "ok" if not failed_repos else "error",
            "ok" if not failed_repos else f"{len(failed_repos)} repo(s) with issues",
        ))

    url = (os.environ.get("LLM_MODEL_URL") or "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL_NAME")
    running, msg = _neo4j_running()
    avail.append(("neo4j", "ok" if running else "warn", msg))

    if url and api_key and model:
        explicit = os.environ.get("LLM_SERVER_URL")
        server_url = explicit.rstrip("/") if explicit else _infer_llm_server_url(url)
        inference_path = os.environ.get("LLM_INFERENCE_ENDPOINT", _LLM_DEFAULT_INFERENCE_PATH)
        passed, msg = _check_llm_server(server_url)
        if passed:
            passed, msg = _check_llm_auth(server_url, api_key)
        if passed:
            passed, msg = _check_llm_model(server_url, api_key, model)
        if passed:
            passed, msg = _check_llm_inference_endpoint(url, api_key, inference_path)
        if passed:
            passed, msg = _check_llm_inference(url, api_key, model, inference_path)
        avail.append(("llm", "ok" if passed else "error", msg))
    else:
        avail.append(("llm", "warn", "skipped"))

    lo_cfg_status, _ = component_config_check("llm-observability")
    if lo_cfg_status != "ok":
        avail.append(("llm-observability", "warn", "not configured"))
    else:
        running, msg = _llm_obs_running()
        avail.append(("llm-observability", "ok" if running else "warn", msg))

    from .plugin import _REGISTRY
    for plugin in _REGISTRY:
        if plugin.check_availability is not None:
            passed, msg = plugin.check_availability()
            avail.append((plugin.name, "ok" if passed else "error", msg))
        else:
            avail.append((plugin.name, "warn", "no availability check"))

    return config, avail
