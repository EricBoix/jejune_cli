import subprocess
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from jejune_cli import click_comp_ecosystem
from jejune_cli.component_ecosystem import CompEcosystem, EcosystemDirectories

REMOTE_URL = "https://example.org/team/pdf-to-markdown.git"


class FakeGitAccess:
    """Records the git commands and plays the remote probe."""

    def __init__(self, probe_returncode=0, probe_error=None):
        self.probe_returncode = probe_returncode
        self.probe_error = probe_error
        self.git_commands = []

    def ls_remote_anonymous(self, arguments, timeout):
        if self.probe_error:
            raise self.probe_error
        return SimpleNamespace(returncode=self.probe_returncode)

    def run_git(self, arguments, repository_url=None, token_file=None, **run_options):
        self.git_commands.append(arguments)
        return SimpleNamespace(returncode=0)

    def origin_url(self, repo_path):
        return REMOTE_URL


@pytest.fixture
def make_ecosystem():
    def make(git_access=None):
        return CompEcosystem(
            SimpleNamespace(
                name="git-server",
                remote_repo_path=lambda name: f"https://example.org/team/{name}",
                remote_git_url=lambda name, fragment=None: REMOTE_URL,
            ),
            git_access or FakeGitAccess(),
            SimpleNamespace(),
            SimpleNamespace(),
        )

    return make


def test_registration_is_idempotent_and_filtered_by_component(make_ecosystem):
    ecosystem = make_ecosystem()
    ecosystem.register_repository("converters", "pdf-to-markdown")
    ecosystem.register_repository("converters", "pdf-to-markdown")
    ecosystem.register_repository("other", "another-repository")
    assert ecosystem.registered_repositories(["converters"]) == ["pdf-to-markdown"]
    assert ecosystem.registered_repositories(["converters", "other"]) == [
        "another-repository",
        "pdf-to-markdown",
    ]
    assert ecosystem.registered_repositories(["unknown"]) == []


@pytest.mark.parametrize("tier", ["root", "tmp"])
def test_local_repository_state_is_the_clone_one(tier, tmp_path, make_ecosystem):
    (tmp_path / "pdf-to-markdown").mkdir()
    ecosystem = make_ecosystem()
    ecosystem.repo_up_to_date = lambda path: True
    directories = (
        EcosystemDirectories(tmp_path, None)
        if tier == "root"
        else EcosystemDirectories(None, tmp_path)
    )
    state = ecosystem.repository_state("pdf-to-markdown", directories)
    assert state.location.tier == tier
    assert state.location.local_path == tmp_path / "pdf-to-markdown"
    assert state.up_to_date is True
    assert state.remote_url is None
    assert state.is_available


@pytest.mark.parametrize(
    "probe_returncode, expected_reachable",
    [(0, True), (2, True), (128, False)],
)
def test_remote_repository_state_probes_the_remote_on_demand(
    probe_returncode, expected_reachable, make_ecosystem
):
    ecosystem = make_ecosystem(FakeGitAccess(probe_returncode))
    directories = EcosystemDirectories(None, None)
    not_probed = ecosystem.repository_state("pdf-to-markdown", directories)
    assert (not_probed.remote_url, not_probed.reachable) == (REMOTE_URL, None)
    assert not not_probed.is_available
    probed = ecosystem.repository_state(
        "pdf-to-markdown", directories, probe_remote=True
    )
    assert probed.reachable is expected_reachable
    assert probed.is_available is expected_reachable


@pytest.mark.parametrize(
    "probe_error", [subprocess.TimeoutExpired("git", 15), FileNotFoundError("git")]
)
def test_unreachable_remote_when_git_fails_to_run(probe_error, make_ecosystem):
    ecosystem = make_ecosystem(FakeGitAccess(probe_error=probe_error))
    assert ecosystem.remote_reachable(REMOTE_URL) is False


def git(repository_path, *arguments):
    subprocess.run(
        ["git", "-C", str(repository_path), *arguments],
        check=True,
        capture_output=True,
    )


def test_unshallow_only_fetches_for_a_shallow_clone(tmp_path, make_ecosystem):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    for commit_number in range(2):
        (origin / "file").write_text(str(commit_number))
        git(origin, "add", "file")
        git(
            origin,
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.org",
            "commit",
            "-q",
            "-m",
            str(commit_number),
        )
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(shallow)],
        check=True,
    )
    complete = tmp_path / "complete"
    subprocess.run(["git", "clone", "-q", origin.as_uri(), str(complete)], check=True)

    git_access = FakeGitAccess()
    ecosystem = make_ecosystem(git_access)
    ecosystem.unshallow(complete)
    assert git_access.git_commands == []
    ecosystem.unshallow(shallow)
    assert git_access.git_commands == [["-C", str(shallow), "fetch", "--unshallow"]]


class FakeComponentRegistry:
    def __init__(self, components):
        self._components = components

    def get(self, name):
        return self._components[name]

    def __iter__(self):
        return iter(self._components.values())


class FakeComponent:
    """Hashable, as the components of the role are kept in a set."""

    def __init__(self, name, **attributes):
        self.name = name
        self.__dict__.update(attributes)


class FakeApplication:
    """What `ecosystem status` needs: a catalog-contributor role whose only active
    component is `converters`."""

    def __init__(self, ecosystem):
        converters = FakeComponent("converters")
        self.component_registry = FakeComponentRegistry(
            {
                "converters": converters,
                "ecosystem": ecosystem,
                "git-server": FakeComponent(
                    "git-server", repo_root_dir=lambda: "https://example.org/team"
                ),
            }
        )
        self.role_registry = SimpleNamespace(
            detect_role=lambda: SimpleNamespace(name="catalog-contributor"),
            role_components=lambda role: {converters},
        )
        self.plugin_registry = SimpleNamespace(repo_name_for_plugin=lambda name: None)


def status_output(monkeypatch, tmp_path, ecosystem, directories):
    ecosystem.register_repository("converters", "pdf-to-markdown")
    ecosystem.resolve_dirs = lambda deploy_dir=None: directories
    ecosystem.discover_doc_repos = lambda directories, remote_names=None: []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(click_comp_ecosystem, "AppContext", FakeApplication)
    result = CliRunner().invoke(
        click_comp_ecosystem.ecosystem_status, [], obj=FakeApplication(ecosystem)
    )
    assert result.exit_code == 0, result.output
    return result.output


def pdf_to_markdown_row(output):
    rows = [line for line in output.splitlines() if "pdf-to-markdown" in line]
    assert len(rows) == 1, output
    return rows[0]


def test_status_lists_pdf_to_markdown_not_cloned_with_its_remote(
    monkeypatch, tmp_path, make_ecosystem
):
    reachable = make_ecosystem(FakeGitAccess(probe_returncode=0))
    row = pdf_to_markdown_row(
        status_output(
            monkeypatch, tmp_path, reachable, EcosystemDirectories(None, None)
        )
    )
    assert REMOTE_URL in row and "✓" in row and "✗" not in row


def test_status_flags_pdf_to_markdown_with_an_unreachable_remote(
    monkeypatch, tmp_path, make_ecosystem
):
    unreachable = make_ecosystem(FakeGitAccess(probe_returncode=128))
    row = pdf_to_markdown_row(
        status_output(
            monkeypatch, tmp_path, unreachable, EcosystemDirectories(None, None)
        )
    )
    assert REMOTE_URL in row and "✗" in row and "✓" not in row


@pytest.mark.parametrize(
    "tier, clone_label", [("root", "[JEJUNE_ROOT_DIR]"), ("tmp", "[.jejune/tmp]")]
)
def test_status_shows_where_pdf_to_markdown_is_cloned(
    tier, clone_label, monkeypatch, tmp_path, make_ecosystem
):
    (tmp_path / "pdf-to-markdown").mkdir()
    ecosystem = make_ecosystem(FakeGitAccess(probe_returncode=128))
    ecosystem.repo_up_to_date = lambda path: True
    directories = (
        EcosystemDirectories(tmp_path, None)
        if tier == "root"
        else EcosystemDirectories(None, tmp_path)
    )
    row = pdf_to_markdown_row(
        status_output(monkeypatch, tmp_path, ecosystem, directories)
    )
    # A cloned repository is not probed: an unreachable remote does not matter
    assert clone_label in row and REMOTE_URL not in row and "✗" not in row
