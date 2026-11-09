import subprocess
from types import SimpleNamespace

import pytest

from jejune_cli.component_git_access import CompGitAccess

PUBLIC_URL = "https://example.org/team/jejune_doc_Public"
PRIVATE_URL = "https://example.org/team/jejune_doc_Private"


@pytest.fixture
def git_access(monkeypatch):
    monkeypatch.delenv(CompGitAccess.TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(CompGitAccess.TOKEN_FILE_ENV_VAR, raising=False)
    return CompGitAccess(git_command=SimpleNamespace(name="git-command"))


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "token"
    path.write_text("alice:ghp_secret\n")
    path.chmod(0o600)
    return path


@pytest.fixture
def catalog_path(tmp_path, token_file):
    path = tmp_path / "catalog.yaml"
    path.write_text(
        "documents:\n"
        "  - name: jejune_doc_Public\n"
        f"    url: {PUBLIC_URL}\n"
        "    public: true\n"
        "  - name: jejune_doc_Private\n"
        f"    url: {PRIVATE_URL}\n"
        "    public: false\n"
        f"    token_file: {token_file}\n"
    )
    return path


def fake_run_git(git_access, monkeypatch, unreachable_urls=()):
    calls = []

    def run_git(arguments, repository_url=None, token_file=None, **run_options):
        calls.append((arguments, repository_url, token_file))
        returncode = 128 if repository_url in unreachable_urls else 0
        return subprocess.CompletedProcess(arguments, returncode)

    monkeypatch.setattr(git_access, "run_git", run_git)
    return calls


def test_probe_uses_the_key_of_each_entry(git_access, catalog_path, token_file, monkeypatch):
    calls = fake_run_git(git_access, monkeypatch)
    rows = git_access.probe_catalog(catalog_path)
    assert [status for status, _, _ in rows] == ["ok", "ok"]
    assert all("reachable" in message for _, _, message in rows)
    assert calls == [
        (["ls-remote", PUBLIC_URL, "HEAD"], PUBLIC_URL, None),
        (["ls-remote", PRIVATE_URL, "HEAD"], PRIVATE_URL, str(token_file)),
    ]


def test_probe_reports_wrong_url_or_no_access(git_access, catalog_path, monkeypatch):
    fake_run_git(git_access, monkeypatch, unreachable_urls=[PRIVATE_URL])
    rows = git_access.probe_catalog(catalog_path)
    assert rows[0][0] == "ok"
    status, subject, message = rows[1]
    assert status == "error"
    assert subject.endswith("catalog.yaml:8")
    assert "not reachable: wrong url or no access" in message


def test_probe_skips_entries_without_usable_key(git_access, tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "documents:\n"
        "  - name: jejune_doc_Private\n"
        f"    url: {PRIVATE_URL}\n"
        "    public: false\n"
    )
    calls = fake_run_git(git_access, monkeypatch)
    assert git_access.probe_catalog(catalog_path) == []
    assert calls == []
    # the local check is the one reporting the missing key
    assert git_access.check_catalog(catalog_path)[0][0] == "error"


def test_probe_reports_timeout(git_access, catalog_path, monkeypatch):
    def run_git(arguments, repository_url=None, token_file=None, **run_options):
        raise subprocess.TimeoutExpired(arguments, run_options["timeout"])

    monkeypatch.setattr(git_access, "run_git", run_git)
    rows = git_access.probe_catalog(catalog_path)
    assert {status for status, _, _ in rows} == {"error"}
    assert "no answer" in rows[0][2]


def test_local_check_says_well_formed_not_valid(git_access, catalog_path):
    message = git_access.check_catalog(catalog_path)[1][2]
    assert "is well-formed" in message
