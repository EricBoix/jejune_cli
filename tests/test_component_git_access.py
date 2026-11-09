import subprocess
from types import SimpleNamespace

import pytest

from jejune_cli.component_catalog_access_checker import CatalogAccessChecker
from jejune_cli.component_cont_convert import CompConvert
from jejune_cli.component_git_access import CompGitAccess

# Reserved example domain: the tests must not depend on the default ecosystem host
REPOSITORY_HOST_AND_PATH = "example.org/team/jejune_doc_X.git"
REPOSITORY_URL = f"https://{REPOSITORY_HOST_AND_PATH}"


@pytest.fixture
def git_access():
    return CompGitAccess(git_command=SimpleNamespace(name="git-command"))


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "token"
    path.write_text("alice:ghp_a:b\n")
    path.chmod(0o600)
    return path


def test_read_token_file_splits_at_first_colon(token_file):
    assert CompGitAccess.read_token_file(token_file) == ("alice", "ghp_a:b")


def test_read_token_file_rejects_raw_token(tmp_path):
    raw_token = tmp_path / "raw"
    raw_token.write_text("ghp_onlyatoken\n")
    with pytest.raises(ValueError):
        CompGitAccess.read_token_file(raw_token)


def test_validate_token_file_rejects_group_readable_file(token_file):
    token_file.chmod(0o640)
    status, message = CompGitAccess.validate_token_file(str(token_file))
    assert status == "error" and "chmod 600" in message


def test_validate_token_file_rejects_missing_file(tmp_path):
    status, _ = CompGitAccess.validate_token_file(str(tmp_path / "absent"))
    assert status == "error"


def test_credentials_line_is_path_aware_and_encoded():
    line = CompGitAccess.credentials_line(REPOSITORY_URL, "alice", "p@ss:word")
    assert line == f"https://alice:p%40ss%3Aword@{REPOSITORY_HOST_AND_PATH}"


def test_credentials_file_has_mode_0600_and_is_removed(
    git_access, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with git_access.credentials_file([REPOSITORY_URL], token_file) as credentials:
        assert credentials.stat().st_mode & 0o777 == 0o600
        assert credentials.read_text() == (
            f"https://alice:ghp_a%3Ab@{REPOSITORY_HOST_AND_PATH}\n"
        )
    assert not credentials.exists()


def test_credentials_file_is_none_without_token_file(git_access, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CompGitAccess.TOKEN_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv(CompGitAccess.TOKEN_ENV_VAR, raising=False)
    with git_access.credentials_file([REPOSITORY_URL]) as credentials:
        assert credentials is None


def test_credentials_file_uses_environment_variable(
    git_access, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(CompGitAccess.TOKEN_FILE_ENV_VAR, str(token_file))
    with git_access.credentials_file([REPOSITORY_URL]) as credentials:
        assert credentials is not None


def test_credentials_file_uses_token_variable_and_file_wins(
    git_access, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(CompGitAccess.TOKEN_ENV_VAR, "bob:variable_token")
    with git_access.credentials_file([REPOSITORY_URL]) as credentials:
        assert "bob:variable_token@" in credentials.read_text()
    with git_access.credentials_file([REPOSITORY_URL], token_file) as credentials:
        assert "alice:" in credentials.read_text()


def test_check_requires_one_valid_source(git_access, token_file, monkeypatch):
    monkeypatch.delenv(CompGitAccess.TOKEN_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv(CompGitAccess.TOKEN_ENV_VAR, raising=False)
    assert git_access.check() == ("ok", "")
    monkeypatch.setenv(CompGitAccess.TOKEN_ENV_VAR, "raw")
    assert git_access.check()[0] == "error"
    monkeypatch.setenv(CompGitAccess.TOKEN_ENV_VAR, "bob:secret")
    assert git_access.check() == ("ok", "")


def test_credentials_file_rejects_invalid_token_file(git_access, tmp_path):
    invalid = tmp_path / "invalid"
    invalid.write_text("raw\n")
    invalid.chmod(0o600)
    with pytest.raises(ValueError):
        with git_access.credentials_file([REPOSITORY_URL], invalid):
            pass


def test_dockerfile_git_urls_ignores_comments(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "RUN set -ex \\\n"
        "    && git -c credential.useHttpPath=true \\\n"
        "           -c credential.helper='store --file=/run/secrets/git_credentials' \\\n"
        f"           clone {REPOSITORY_URL} \\\n"
        "    # clone https://example.org/commented.git\n"
        "RUN git clone --depth 1 https://example.org/other.git\n"
    )
    assert CompConvert.dockerfile_git_urls(dockerfile) == [
        REPOSITORY_URL,
        "https://example.org/other.git",
    ]


def test_convert_build_passes_credentials_as_docker_secret(
    git_access, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    docker_context = tmp_path / "DockerContext"
    docker_context.mkdir()
    (docker_context / "Dockerfile").write_text(f"RUN git clone {REPOSITORY_URL}\n")
    monkeypatch.setenv("CONVERT_DOC_DIR", str(tmp_path))
    commands = []
    monkeypatch.setattr(
        subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    convert = CompConvert.__new__(CompConvert)
    convert._context = SimpleNamespace(git_access=git_access)
    convert.configuration = SimpleNamespace(check=lambda: ("ok", "", ""))

    convert.build(token_file=token_file)
    convert.build()
    monkeypatch.delenv(CompGitAccess.TOKEN_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv(CompGitAccess.TOKEN_ENV_VAR, raising=False)

    with_secret, without_secret = commands
    assert "--secret" in with_secret
    assert with_secret[with_secret.index("--secret") + 1].startswith(
        "id=git_credentials,src="
    )
    assert "--secret" not in without_secret


def test_credentials_file_for_entries_uses_one_token_file_per_repository(
    git_access, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CompGitAccess.TOKEN_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv(CompGitAccess.TOKEN_ENV_VAR, raising=False)
    other_token_file = tmp_path / "other"
    other_token_file.write_text("bob:other_token\n")
    other_token_file.chmod(0o600)
    other_url = "https://example.org/team/jejune_doc_Y.git"
    with git_access.credentials_file_for_entries(
        [
            (REPOSITORY_URL, token_file),
            (other_url, other_token_file),
            ("https://x/y", None),
        ]
    ) as credentials:
        assert credentials.read_text().splitlines() == [
            f"https://alice:ghp_a%3Ab@{REPOSITORY_HOST_AND_PATH}",
            "https://bob:other_token@example.org/team/jejune_doc_Y.git",
        ]


def test_run_git_authenticates_only_with_a_token(
    git_access, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CompGitAccess.TOKEN_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv(CompGitAccess.TOKEN_ENV_VAR, raising=False)
    commands = []
    monkeypatch.setattr(
        subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    git_access.run_git(["ls-remote", REPOSITORY_URL], REPOSITORY_URL)
    git_access.run_git(["ls-remote", REPOSITORY_URL], REPOSITORY_URL, token_file)
    anonymous, authenticated = commands
    assert anonymous == ["git", "ls-remote", REPOSITORY_URL]
    assert authenticated[:5] == [
        "git",
        "-c",
        "credential.useHttpPath=true",
        "-c",
        "credential.helper=",
    ]
    assert authenticated[5:7][0] == "-c"
    assert authenticated[6].startswith("credential.helper=store --file=")
    assert "ghp_a" not in " ".join(authenticated)
    assert authenticated[-2:] == ["ls-remote", REPOSITORY_URL]
    assert not list((tmp_path / ".jejune" / "tmp").glob("git-credentials-*"))


def test_catalog_access_checker_rejects_url_without_repository_path(git_access, tmp_path):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        "documents:\n"
        "  - name: jejune_doc_X\n"
        "    url: https://example.org/team/\n"
        "    public: true\n"
    )
    rows = CatalogAccessChecker(git_access, catalog).run()
    assert len(rows) == 1
    status, location, message = rows[0]
    assert status == "error"
    assert location == f"{catalog}:3"
    assert "<owner>/<repository>" in message


def test_catalog_access_checker_accepts_url_with_repository_path(git_access, tmp_path):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        f"documents:\n  - name: jejune_doc_X\n    url: {REPOSITORY_URL}\n"
        "    public: true\n"
    )
    assert [status for status, _, _ in CatalogAccessChecker(git_access, catalog).run()] == ["ok"]
