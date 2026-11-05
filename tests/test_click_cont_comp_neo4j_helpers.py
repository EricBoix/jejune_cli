import click
import pytest

from jejune_cli.click_cont_comp_neo4j_helpers import resolve_restore_dump_location


@pytest.fixture
def results_dir(tmp_path):
    results_directory = tmp_path / "results"
    (results_directory / "backups").mkdir(parents=True)
    return results_directory


@pytest.fixture
def temporary_directory(tmp_path):
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    return temporary


def test_simple_filename_uses_default_backups(results_dir, temporary_directory):
    assert resolve_restore_dump_location(
        results_dir, "my.dump", temporary_directory
    ) == (None, "my.dump")
    assert list(temporary_directory.iterdir()) == []


def test_relative_path_elsewhere_is_copied(
    results_dir, temporary_directory, tmp_path, monkeypatch
):
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "my.dump").write_text("content")
    monkeypatch.chdir(tmp_path)
    backups_dir, dump_name = resolve_restore_dump_location(
        results_dir, "./other/my.dump", temporary_directory
    )
    assert backups_dir == temporary_directory
    assert dump_name == "my.dump"
    assert (temporary_directory / "my.dump").read_text() == "content"


def test_dump_in_current_directory_with_dot_slash(
    results_dir, temporary_directory, tmp_path, monkeypatch
):
    (tmp_path / "my.dump").write_text("content")
    monkeypatch.chdir(tmp_path)
    backups_dir, dump_name = resolve_restore_dump_location(
        results_dir, "./my.dump", temporary_directory
    )
    assert backups_dir == temporary_directory
    assert (temporary_directory / "my.dump").exists()


def test_path_already_in_backups_is_not_copied(
    results_dir, temporary_directory, monkeypatch
):
    (results_dir / "backups" / "my.dump").write_text("content")
    monkeypatch.chdir(results_dir)
    assert resolve_restore_dump_location(
        results_dir, "backups/my.dump", temporary_directory
    ) == (None, "my.dump")
    assert list(temporary_directory.iterdir()) == []


def test_absolute_path_elsewhere_is_copied(
    results_dir, temporary_directory, tmp_path
):
    (tmp_path / "my.dump").write_text("content")
    backups_dir, dump_name = resolve_restore_dump_location(
        results_dir, str(tmp_path / "my.dump"), temporary_directory
    )
    assert backups_dir == temporary_directory
    assert dump_name == "my.dump"


def test_nonexistent_path_raises(results_dir, temporary_directory, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(click.ClickException):
        resolve_restore_dump_location(
            results_dir, "./missing/my.dump", temporary_directory
        )
