import subprocess
from types import SimpleNamespace

import pytest

from jejune_cli.component_ecosystem import CompEcosystem
from jejune_cli.component_git_access import CompGitAccess

PUBLIC_URL = "https://example.org/team/jejune_doc_Public"
PRIVATE_URL = "https://example.org/team/jejune_doc_Private"


@pytest.fixture
def git_access(monkeypatch):
    monkeypatch.delenv(CompGitAccess.TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(CompGitAccess.TOKEN_FILE_ENV_VAR, raising=False)
    return CompGitAccess(git_command=SimpleNamespace(name="git-command"))


@pytest.fixture
def ecosystem(git_access, tmp_path, monkeypatch):
    monkeypatch.delenv("JEJUNE_ROOT_DIR", raising=False)
    git_server = SimpleNamespace(
        name="git-server", remote_repo_path=lambda name: f"remote/{name}"
    )
    ecosystem = CompEcosystem(git_server, git_access, None, None)
    ecosystem.cloned = []
    ecosystem.updated = []

    def record_clone(repository_url, destination, token_file=None):
        ecosystem.cloned.append((repository_url, destination.name, token_file))

    def record_update(repo_path, token_file=None):
        ecosystem.updated.append((repo_path.name, token_file))
        return True

    monkeypatch.setattr(ecosystem, "clone_repository", record_clone)
    monkeypatch.setattr(ecosystem, "update_tmp_repo", record_update)
    return ecosystem


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "token"
    path.write_text("alice:ghp_secret\n")
    path.chmod(0o600)
    return path


def write_catalog(tmp_path, token_line=""):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "documents:\n"
        "  - name: jejune_doc_Public\n"
        f"    url: {PUBLIC_URL}\n"
        "    public: true\n"
        "  - name: jejune_doc_Private\n"
        f"    url: {PRIVATE_URL}\n"
        "    public: false\n"
        f"{token_line}"
    )
    return catalog_path


def outcome_statuses(outcomes):
    return {outcome.name: outcome.status for outcome in outcomes}


def test_missing_entries_are_cloned_with_their_own_token_file(
    ecosystem, token_file, tmp_path
):
    catalog_path = write_catalog(tmp_path, f"    token_file: {token_file}\n")
    outcomes = ecosystem.update_catalog_repos(catalog_path, deploy_dir=tmp_path)
    assert outcome_statuses(outcomes) == {
        "jejune_doc_Public": "cloned",
        "jejune_doc_Private": "cloned",
    }
    assert ecosystem.cloned == [
        (PUBLIC_URL, "jejune_doc_Public", None),
        (PRIVATE_URL, "jejune_doc_Private", str(token_file)),
    ]


def test_cloned_entries_are_updated(ecosystem, token_file, tmp_path):
    catalog_path = write_catalog(tmp_path, f"    token_file: {token_file}\n")
    for name in ("jejune_doc_Public", "jejune_doc_Private"):
        (tmp_path / ".jejune" / "tmp" / name).mkdir(parents=True)
    outcomes = ecosystem.update_catalog_repos(catalog_path, deploy_dir=tmp_path)
    assert outcome_statuses(outcomes) == {
        "jejune_doc_Public": "updated",
        "jejune_doc_Private": "updated",
    }
    assert ecosystem.updated == [
        ("jejune_doc_Public", None),
        ("jejune_doc_Private", str(token_file)),
    ]


def test_private_entry_without_any_key_fails_and_others_are_still_pulled(
    ecosystem, tmp_path
):
    outcomes = ecosystem.update_catalog_repos(write_catalog(tmp_path), tmp_path)
    assert outcome_statuses(outcomes) == {
        "jejune_doc_Public": "cloned",
        "jejune_doc_Private": "failed",
    }
    assert "no `token_file`" in outcomes[1].message
    assert [name for _, name, _ in ecosystem.cloned] == ["jejune_doc_Public"]


def test_private_entry_with_invalid_token_file_fails(ecosystem, tmp_path):
    missing = tmp_path / "missing"
    catalog_path = write_catalog(tmp_path, f"    token_file: {missing}\n")
    outcomes = ecosystem.update_catalog_repos(catalog_path, deploy_dir=tmp_path)
    assert outcomes[1].status == "failed"
    assert "token file not found" in outcomes[1].message


def test_private_entry_uses_environment_key(ecosystem, token_file, tmp_path, monkeypatch):
    monkeypatch.setenv(CompGitAccess.TOKEN_FILE_ENV_VAR, str(token_file))
    outcomes = ecosystem.update_catalog_repos(write_catalog(tmp_path), tmp_path)
    assert outcome_statuses(outcomes)["jejune_doc_Private"] == "cloned"


def test_git_failure_is_reported(ecosystem, token_file, tmp_path, monkeypatch):
    def refuse(*arguments, **options):
        raise subprocess.CalledProcessError(128, ["git", "clone"])

    monkeypatch.setattr(ecosystem, "clone_repository", refuse)
    catalog_path = write_catalog(tmp_path, f"    token_file: {token_file}\n")
    outcomes = ecosystem.update_catalog_repos(catalog_path, deploy_dir=tmp_path)
    assert {outcome.status for outcome in outcomes} == {"failed"}
    assert "status 128" in outcomes[0].message


def test_malformed_entry_fails_without_stopping_the_others(ecosystem, tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        f"documents:\n  - public: true\n  - name: jejune_doc_Public\n    url: {PUBLIC_URL}\n"
    )
    outcomes = ecosystem.update_catalog_repos(catalog_path, deploy_dir=tmp_path)
    assert outcome_statuses(outcomes) == {
        "entry #1": "failed",
        "jejune_doc_Public": "cloned",
    }


def test_entry_found_in_root_dir_is_skipped(ecosystem, tmp_path, monkeypatch):
    root_dir = tmp_path / "root"
    (root_dir / "jejune_doc_Public").mkdir(parents=True)
    monkeypatch.setenv("JEJUNE_ROOT_DIR", str(root_dir))
    outcomes = ecosystem.update_catalog_repos(write_catalog(tmp_path), tmp_path)
    assert outcome_statuses(outcomes)["jejune_doc_Public"] == "skipped"
    assert ecosystem.updated == []


def test_ensure_local_clones_a_catalog_repository_with_its_own_url_and_token_file(
    ecosystem, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    write_catalog(tmp_path, f"    token_file: {token_file}\n")
    ecosystem.ensure_local("jejune_doc_Private")
    assert ecosystem.cloned == [(PRIVATE_URL, "jejune_doc_Private", str(token_file))]


def test_locate_prefers_root_then_tmp_then_remote(ecosystem, tmp_path):
    root_dir, tmp_dir = tmp_path / "root", tmp_path / "tmp"
    (root_dir / "in_root").mkdir(parents=True)
    (tmp_dir / "in_tmp").mkdir(parents=True)
    (root_dir / "both").mkdir()
    (tmp_dir / "both").mkdir()
    assert ecosystem.locate("both", root_dir, tmp_dir).tier == "root"
    assert ecosystem.locate("in_tmp", root_dir, tmp_dir).local_path == tmp_dir / "in_tmp"
    remote = ecosystem.locate("elsewhere", root_dir, tmp_dir)
    assert (remote.tier, remote.is_local, remote.remote_path) == (
        "remote",
        False,
        "remote/elsewhere",
    )
