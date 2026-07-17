import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import click
import yaml

from .env import dot_jejune

_TEMPLATES = Path(__file__).parent / "templates"
_INFERENCE_TEST_PROMPT = "How are you today?"
_INFERENCE_TIMEOUT = 10  # seconds
_PLACEHOLDER = "_CHANGE_ME"

# Env-var groups: name → (variables, commands that require them).
# "warn" (yellow) = none set — use case not configured, valid.
# "error" (red)   = partial or placeholder — needs attention.
_ENV_GROUPS: dict[str, tuple[list[str], str]] = {
    "neo4j":     (["NEO4J_PASSWORD"],                              "build neo4j-*, kg-extract, dump-turtle"),
    "llm":       (["LLM_MODEL_URL", "LLM_API_KEY", "LLM_MODEL_NAME"], "build kg-extract"),
    "workspace": (["JJ_ROOT_DIR"],                                 "test pdf-to-markdown, configure check-catalog"),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_env_group(keys: list[str]) -> tuple[str, str]:
    """Check a group of env vars; return (status, message).

    status is "ok", "warn" (none set — use case not configured), or "error"
    (partial fill or placeholder values present).
    """
    states: list[tuple[str, str]] = []
    for key in keys:
        val = os.environ.get(key)
        if val is None:
            states.append((key, "missing"))
        elif _PLACEHOLDER in val:
            states.append((key, "placeholder"))
        else:
            states.append((key, "ok"))

    if all(s == "ok" for _, s in states):
        return "ok", "ok"
    if all(s == "missing" for _, s in states):
        return "warn", "not configured"
    issues = [f"{k}: {s}" for k, s in states if s != "ok"]
    return "error", "; ".join(issues)


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
        # else: private repo absent from reference — expected

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
    to_add: list[tuple[str, str]] = []  # (name, url)

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
            results.append((name, False, f"public repo missing from catalog"))
            to_add.append((name, url))

    if do_add and to_add and catalog.exists():
        with catalog.open("a") as f:
            for name, url in to_add:
                f.write(f"  - name: {name}\n")
                f.write(f"    url: {url}\n")
                f.write(f"    public: true\n")
        click.echo(f"Added {len(to_add)} repo(s) to {catalog}.")

    return results


def _do_test_inference(
    url: str, api_key: str, model: str, prompt: str = _INFERENCE_TEST_PROMPT
) -> tuple[bool, str]:
    """Run both LLM connectivity checks; return (passed, message)."""
    auth = {"Authorization": f"BEARER {api_key}"}

    req = urllib.request.Request(f"{url}/api/tags", headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=_INFERENCE_TIMEOUT) as resp:
            resp.read()
    except urllib.error.URLError as e:
        return False, f"server unreachable: {e.reason}"

    payload = json.dumps({"model": model, "prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=payload,
        headers={**auth, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_INFERENCE_TIMEOUT) as resp:
            resp.read()
    except urllib.error.URLError as e:
        return False, f"inference failed: {e.reason}"

    return True, "ok"


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------

@click.group()
def configure():
    """Stage 1 — verify workspace coherence (read-only, no side-effects)."""


@configure.command("init")
def init():
    """Write jejune scaffold files into .jejune/ in the current directory.

    Creates .jejune/env-config, .jejune/env-secrets, and
    .jejune/catalog.yaml from built-in templates.
    Adds .jejune to .gitignore so the whole directory stays local by default.
    """
    d = dot_jejune()
    d.mkdir(exist_ok=True)

    created = []
    skipped = []
    for fname in ("env-config", "env-secrets", "catalog.yaml"):
        dst = d / fname
        if dst.exists():
            skipped.append(fname)
        else:
            shutil.copy2(_TEMPLATES / fname, dst)
            created.append(fname)

    for f in created:
        click.echo(click.style(f"  created  .jejune/{f}", fg="green"))
    for f in skipped:
        click.echo(click.style(f"  skipped  .jejune/{f} (already exists)", fg="yellow"))

    gitignore = Path.cwd() / ".gitignore"
    entry = ".jejune\n"
    if not gitignore.exists() or ".jejune" not in gitignore.read_text().splitlines():
        with gitignore.open("a") as fh:
            fh.write(entry)
        click.echo(click.style("  updated  .gitignore (.jejune)", fg="green"))

    click.echo()
    click.echo("Next step: edit .jejune/env-secrets with your credentials.")


@configure.command("check-env")
def check_env():
    """Verify env-secrets variables by use-case group.

    Reports each group (neo4j, llm, workspace) independently:\n
      ok            — all vars set and non-placeholder\n
      not configured — none set (use case not activated, not an error)\n
      error         — partial or placeholder values (needs attention)\n

    Checks os.environ, which already includes values loaded from
    .jejune/env-config and .jejune/env-secrets at startup.
    """
    any_error = False
    for group, (keys, usage) in _ENV_GROUPS.items():
        status, msg = _check_env_group(keys)
        if status == "ok":
            label = click.style(f"{'ok':<26}", fg="green")
        elif status == "warn":
            label = click.style(f"{msg:<26}", fg="yellow")
        else:
            label = click.style(f"{msg:<26}", fg="red")
            any_error = True
        click.echo(f"  {group:<16} {label} {usage}")

    if any_error:
        raise SystemExit(1)


@configure.command("check-catalog")
@click.option(
    "--catalog",
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
def check_catalog(catalog, root_dir):
    """Verify catalog.yaml against GitHub visibility and local clones.

    For each entry: confirms the public flag matches actual GitHub visibility
    and that a local clone exists under JJ_ROOT_DIR.
    Requires the gh CLI to be authenticated.
    """
    cat_path = Path(catalog) if catalog else dot_jejune() / "catalog.yaml"
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


@configure.command("sync-catalog")
@click.option(
    "--catalog",
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
def sync_catalog(catalog, root_dir, do_add):
    """Report public jj_doc_* repos under JJ_ROOT_DIR missing from catalog.yaml.

    With --add, appends missing public repos to the catalog file in place.
    Private repos are flagged as informational only — add them manually to
    deployment catalogs as needed.
    """
    if not root_dir:
        raise click.ClickException("JJ_ROOT_DIR is not set. Use --root-dir or set the env var.")

    cat_path = Path(catalog) if catalog else dot_jejune() / "catalog.yaml"
    results = _sync_catalog_impl(cat_path, Path(root_dir), do_add)

    for name, ok, msg in results:
        if ok:
            status = click.style(msg, fg="green")
        else:
            status = click.style(msg, fg="yellow" if "private" in msg else "red")
        click.echo(f"  {name:<45} {status}")


@configure.command("test-inference")
@click.option(
    "--prompt",
    default=_INFERENCE_TEST_PROMPT,
    show_default=True,
    help="Prompt sent to the LLM for the inference round-trip test.",
)
def test_inference(prompt):
    """Test LLM server connectivity and inference capability.

    Reads LLM_MODEL_URL, LLM_API_KEY, LLM_MODEL_NAME from the environment.
    Performs two checks:\n
      1. GET  <LLM_MODEL_URL>/api/tags        — server reachable and authenticated\n
      2. POST <LLM_MODEL_URL>/api/generate    — inference round-trip succeeds\n
    """
    url = os.environ.get("LLM_MODEL_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL_NAME")

    missing = [n for n, v in [
        ("LLM_MODEL_URL", url), ("LLM_API_KEY", api_key), ("LLM_MODEL_NAME", model)
    ] if not v]
    if missing:
        raise click.ClickException(f"Missing environment variables: {', '.join(missing)}")

    click.echo(f"Server : {url}")
    click.echo(f"Model  : {model}")
    click.echo(f"Prompt : {prompt!r}")
    click.echo()

    auth = {"Authorization": f"BEARER {api_key}"}

    click.echo("  [1/2] Server reachability... ", nl=False)
    req = urllib.request.Request(f"{url}/api/tags", headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=_INFERENCE_TIMEOUT) as resp:
            resp.read()
        click.echo(click.style("ok", fg="green"))
    except urllib.error.URLError as e:
        click.echo(click.style(f"FAILED — {e.reason}", fg="red"))
        raise SystemExit(1)

    click.echo("  [2/2] Inference round-trip... ", nl=False)
    payload = json.dumps({"model": model, "prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=payload,
        headers={**auth, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_INFERENCE_TIMEOUT) as resp:
            resp.read()
        click.echo(click.style("ok", fg="green"))
    except urllib.error.URLError as e:
        click.echo(click.style(f"FAILED — {e.reason}", fg="red"))
        raise SystemExit(1)


@configure.command("check-deployment")
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

def run_all() -> list[tuple[str, str, str, str]]:
    """Return [(check_name, status, message, usage), ...] for every automatable check.

    status is "ok" (green), "warn" (yellow — not configured), or "error" (red).
    usage is a short description of which commands require the check to pass.
    """
    results: list[tuple[str, str, str, str]] = []
    d = dot_jejune()

    # check-env: one entry per use-case group
    for group, (keys, usage) in _ENV_GROUPS.items():
        status, msg = _check_env_group(keys)
        results.append((f"env:{group}", status, msg, usage))

    # check-catalog
    root_dir_str = os.environ.get("JJ_ROOT_DIR")
    root_dir = Path(root_dir_str) if root_dir_str else None
    cat_results = _check_catalog_impl(d / "catalog.yaml", root_dir)
    failed_repos = [n for n, ok, _ in cat_results if not ok]
    results.append((
        "check-catalog",
        "ok" if not failed_repos else "error",
        "ok" if not failed_repos else f"{len(failed_repos)} repo(s) with issues",
        "test pdf-to-markdown, configure check-catalog",
    ))

    # test-inference — skip gracefully when llm group is not configured
    url = os.environ.get("LLM_MODEL_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL_NAME")
    if url and api_key and model:
        passed, msg = _do_test_inference(url, api_key, model)
        results.append(("test-inference", "ok" if passed else "error", msg, "build kg-extract"))
    else:
        results.append(("test-inference", "warn", "llm not configured — skipped", "build kg-extract"))

    return results
