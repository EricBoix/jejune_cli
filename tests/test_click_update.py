import json
import subprocess
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from jejune_cli import click_update
from jejune_cli.click_update import JejuneUpdater, update_cmd

GIT_DIRECT_URL = {
    "url": "https://github.com/EricBoix/jejune_cli",
    "vcs_info": {"vcs": "git", "commit_id": "abc"},
}


def _patch_direct_url(monkeypatch, content):
    distribution = SimpleNamespace(read_text=lambda name: content)
    monkeypatch.setattr(
        click_update.importlib.metadata, "distribution", lambda name: distribution
    )


def _record_runs(monkeypatch, return_codes):
    recorded_commands = []

    def fake_run(command):
        recorded_commands.append(command)
        return SimpleNamespace(returncode=return_codes[len(recorded_commands) - 1])

    monkeypatch.setattr(subprocess, "run", fake_run)
    return recorded_commands


def test_git_install_specification(monkeypatch):
    _patch_direct_url(monkeypatch, json.dumps(GIT_DIRECT_URL))
    assert (
        JejuneUpdater().install_specification()
        == "git+https://github.com/EricBoix/jejune_cli"
    )


def test_git_install_specification_keeps_requested_revision(monkeypatch):
    direct_url = {
        "url": GIT_DIRECT_URL["url"],
        "vcs_info": {"vcs": "git", "requested_revision": "dev", "commit_id": "abc"},
    }
    _patch_direct_url(monkeypatch, json.dumps(direct_url))
    assert JejuneUpdater().install_specification().endswith("@dev")


def test_editable_install_is_refused(monkeypatch):
    direct_url = {"url": "file:///src", "dir_info": {"editable": True}}
    _patch_direct_url(monkeypatch, json.dumps(direct_url))
    with pytest.raises(click.ClickException, match="Editable"):
        JejuneUpdater().install_specification()


def test_missing_direct_url_is_refused(monkeypatch):
    _patch_direct_url(monkeypatch, None)
    with pytest.raises(click.ClickException, match="direct_url.json"):
        JejuneUpdater().install_specification()


def test_update_reinstalls_then_installs_plugins(monkeypatch):
    _patch_direct_url(monkeypatch, json.dumps(GIT_DIRECT_URL))
    recorded_commands = _record_runs(monkeypatch, [0, 0])
    result = CliRunner().invoke(update_cmd)
    assert result.exit_code == 0
    assert recorded_commands == [
        [
            "uv",
            "tool",
            "install",
            "--reinstall",
            "--refresh",
            "git+https://github.com/EricBoix/jejune_cli",
        ],
        ["jejune", "plugin-packages", "install"],
    ]


def test_no_plugins_skips_plugin_install(monkeypatch):
    _patch_direct_url(monkeypatch, json.dumps(GIT_DIRECT_URL))
    recorded_commands = _record_runs(monkeypatch, [0])
    result = CliRunner().invoke(update_cmd, ["--no-plugins"])
    assert result.exit_code == 0
    assert len(recorded_commands) == 1


def test_reinstall_failure_aborts_before_plugins(monkeypatch):
    _patch_direct_url(monkeypatch, json.dumps(GIT_DIRECT_URL))
    recorded_commands = _record_runs(monkeypatch, [1])
    result = CliRunner().invoke(update_cmd)
    assert result.exit_code != 0
    assert len(recorded_commands) == 1
