import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from jejune_cli.component_cont_convert import CompConvert
from jejune_cli.component_git_access import CompGitAccess

REPOSITORY_URL = "https://github.com/EricBoix/jejune_doc_X.git"


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
    assert line == ("https://alice:p%40ss%3Aword@github.com/EricBoix/jejune_doc_X.git")


def test_credentials_file_has_mode_0600_and_is_removed(
    git_access, token_file, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with git_access.credentials_file([REPOSITORY_URL], token_file) as credentials:
        assert credentials.stat().st_mode & 0o777 == 0o600
        assert credentials.read_text() == (
            "https://alice:ghp_a%3Ab@github.com/EricBoix/jejune_doc_X.git\n"
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
    assert git_access.check()[0] == "warn"
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
