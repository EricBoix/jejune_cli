import pytest

from jejune_cli.click_configuration import print_config_check
from jejune_cli.configuration import Configuration
from jejune_cli.configuration_entry import ConfigurationEntry


@pytest.fixture
def configuration_with_failures(monkeypatch):
    monkeypatch.setenv("TEST_CONFIG_OK", "value")
    monkeypatch.delenv("TEST_CONFIG_UNSET", raising=False)
    monkeypatch.setenv("TEST_CONFIG_PLACEHOLDER", "CHANGE_ME")
    return [
        ConfigurationEntry(
            "TEST_CONFIG_OK", hint="hint ok", source_file=".jejune/env-config"
        ),
        ConfigurationEntry(
            "TEST_CONFIG_UNSET", hint="hint unset", source_file=".jejune/env-config"
        ),
        ConfigurationEntry(
            "TEST_CONFIG_PLACEHOLDER",
            hint="hint placeholder",
            source_file=".jejune/env-secrets",
        ),
    ]


def test_hints_without_failure_hint_lists_unique_entry_hints():
    configuration = Configuration(
        ConfigurationEntry("A_VAR", hint="edit a"),
        ConfigurationEntry("B_VAR", hint="edit a"),
        ConfigurationEntry("C_VAR", hint="edit c"),
    )
    assert configuration.hints() == ["edit a", "edit c"]


def test_hints_with_failure_hint_returns_only_failure_hint():
    configuration = Configuration(
        ConfigurationEntry("A_VAR", hint="edit a"),
        failure_hint="run `jejune x check-config`",
    )
    assert configuration.hints() == ["run `jejune x check-config`"]


def test_effective_hints_override_wins_over_failure_hint():
    configuration = Configuration(
        ConfigurationEntry("A_VAR", hint="edit a"),
        failure_hint="run `jejune x check-config`",
    )
    assert configuration.effective_hints({"A_VAR": "port busy"}) == ["port busy"]
    assert configuration.effective_hints({}) == ["run `jejune x check-config`"]


def test_check_config_names_file_of_failing_variables(
    configuration_with_failures, capsys
):
    with pytest.raises(SystemExit) as exit_info:
        print_config_check(Configuration(*configuration_with_failures))
    assert exit_info.value.code == 1
    output_lines = capsys.readouterr().out.splitlines()
    assert "ok" in output_lines[0] and "edit" not in output_lines[0]
    assert "edit .jejune/env-config" in output_lines[1]
    assert "edit .jejune/env-secrets" in output_lines[2]


def test_unset_variable_exits_zero_by_default(monkeypatch, capsys):
    monkeypatch.delenv("TEST_CONFIG_UNSET", raising=False)
    configuration = Configuration(
        ConfigurationEntry("TEST_CONFIG_UNSET", source_file=".jejune/env-config")
    )
    print_config_check(configuration)
    assert "not set" in capsys.readouterr().out


def test_unset_variable_exits_one_when_requested(monkeypatch):
    monkeypatch.delenv("TEST_CONFIG_UNSET", raising=False)
    configuration = Configuration(
        ConfigurationEntry("TEST_CONFIG_UNSET", source_file=".jejune/env-config")
    )
    with pytest.raises(SystemExit) as exit_info:
        print_config_check(configuration, exit_on_not_set=True)
    assert exit_info.value.code == 1


def test_all_ok_exits_zero_even_when_requested(monkeypatch):
    monkeypatch.setenv("TEST_CONFIG_OK", "value")
    configuration = Configuration(ConfigurationEntry("TEST_CONFIG_OK"))
    print_config_check(configuration, exit_on_not_set=True)


def test_check_config_reports_validator_error_and_file(monkeypatch, capsys):
    monkeypatch.setenv("TEST_CONFIG_INVALID", "some/value")
    configuration = Configuration(
        ConfigurationEntry(
            "TEST_CONFIG_INVALID",
            source_file=".jejune/env-config",
            env_var_validator=lambda value: ("error", f"{value} lacks DockerContext"),
        )
    )
    with pytest.raises(SystemExit) as exit_info:
        print_config_check(configuration)
    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert "some/value lacks DockerContext" in output
    assert "edit .jejune/env-config" in output
    assert "ok" not in output
