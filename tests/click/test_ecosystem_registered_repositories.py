import subprocess
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from jejune_cli.click import click_group_ecosystem, click_group_git_access
from jejune_cli.components.component_ecosystem import (
    CompEcosystem,
    EcosystemDirectories,
)
from jejune_cli.components.containers.converter_commits import ConverterCommits

REMOTE_URL = "https://example.org/team/pdf-to-markdown.git"
REMOTE_LABEL = "[REPO_ROOT_DIR]/pdf-to-markdown.git"
LOCAL_SHA = "1234567890abcdef"
REMOTE_SHA = "fedcba0987654321"


class FakeGitAccess:
    """Records the git commands and plays the remote probe."""

    def __init__(self, probe_returncode=0, probe_error=None):
        self.probe_returncode = probe_returncode
        self.probe_error = probe_error
        self.git_commands = []

    def run_git(self, arguments, repository_url=None, token_file=None, **run_options):
        self.git_commands.append(arguments)
        return SimpleNamespace(returncode=0)

    def origin_url(self, repo_path):
        return REMOTE_URL

    def head_sha(self, repo_path):
        return LOCAL_SHA

    def ls_remote(self, repository_url, token_file=None, *references, **run_options):
        if self.probe_error:
            raise self.probe_error
        return SimpleNamespace(
            returncode=self.probe_returncode, stdout=f"{REMOTE_SHA}\tHEAD\n"
        )


@pytest.fixture(autouse=True)
def clean_working_tree(monkeypatch):
    """The fake repositories are no git checkouts: they have no uncommitted changes."""
    monkeypatch.setattr(
        ConverterCommits, "has_uncommitted_changes", staticmethod(lambda path: False)
    )


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
            SimpleNamespace(repo_name_for_plugin=lambda name: None),
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


def test_conditional_registration_is_evaluated_at_each_listing(make_ecosystem):
    ecosystem = make_ecosystem()
    condition_holds = {"value": False}
    ecosystem.register_repository(
        "convert", "pdf-to-markdown", when=lambda: condition_holds["value"]
    )
    assert ecosystem.registered_repositories(["convert"]) == []
    condition_holds["value"] = True
    assert ecosystem.registered_repositories(["convert"]) == ["pdf-to-markdown"]


def test_unconditional_registration_prevails_over_a_conditional_one(make_ecosystem):
    ecosystem = make_ecosystem()
    ecosystem.register_repository("convert", "pdf-to-markdown", when=lambda: False)
    ecosystem.register_repository("convert", "pdf-to-markdown")
    ecosystem.register_repository("convert", "pdf-to-markdown", when=lambda: False)
    assert ecosystem.registered_repositories(["convert"]) == ["pdf-to-markdown"]


def test_repository_registered_by_two_components_is_listed_once(make_ecosystem):
    ecosystem = make_ecosystem()
    ecosystem.register_repository("converters", "pdf-to-markdown")
    ecosystem.register_repository("convert", "pdf-to-markdown", when=lambda: True)
    assert ecosystem.registered_repositories(["converters", "convert"]) == [
        "pdf-to-markdown"
    ]


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
    [(0, True), (128, False)],
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
    "probe_error", [subprocess.TimeoutExpired("git", 5), FileNotFoundError("git")]
)
def test_unreachable_remote_when_git_fails_to_run(probe_error, make_ecosystem):
    ecosystem = make_ecosystem(FakeGitAccess(probe_error=probe_error))
    assert ecosystem.probe_remote(REMOTE_URL) == (False, None)


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
    monkeypatch.setattr(click_group_ecosystem, "AppContext", FakeApplication)
    result = CliRunner().invoke(
        click_group_ecosystem.ecosystem_status, [], obj=FakeApplication(ecosystem)
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
    assert REMOTE_LABEL in row and "✓" in row and "✗" not in row
    assert row.endswith(REMOTE_SHA[:7])


def test_status_flags_pdf_to_markdown_with_an_unreachable_remote(
    monkeypatch, tmp_path, make_ecosystem
):
    unreachable = make_ecosystem(FakeGitAccess(probe_returncode=128))
    row = pdf_to_markdown_row(
        status_output(
            monkeypatch, tmp_path, unreachable, EcosystemDirectories(None, None)
        )
    )
    assert REMOTE_LABEL in row and "✗" in row and "✓" not in row
    # An unreachable remote has no commit to show
    assert REMOTE_SHA[:7] not in row


def test_status_header_lists_the_ecosystem_directory_and_the_commit_column(
    monkeypatch, tmp_path, make_ecosystem
):
    output = status_output(
        monkeypatch,
        tmp_path,
        make_ecosystem(),
        EcosystemDirectories(None, None),
    )
    assert any(
        line.split() == ["ECOSYSTEM_DIR", ".jejune/tmp"] for line in output.splitlines()
    )
    header = next(line for line in output.splitlines() if "Component" in line)
    assert header.split() == [
        "Component",
        "Available",
        "Repository",
        "Up-to-date",
        "Commit",
    ]


@pytest.mark.parametrize(
    "tier, clone_label", [("root", "[JEJUNE_ROOT_DIR]"), ("tmp", "[ECOSYSTEM_DIR]")]
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
    assert clone_label in row and REMOTE_LABEL not in row and "✗" not in row
    assert row.endswith(LOCAL_SHA[:7])


def test_repository_states_probe_the_repositories_listed_by_components(make_ecosystem):
    ecosystem = make_ecosystem(FakeGitAccess(probe_returncode=0))
    listing_component = FakeComponent("catalog", repos=[("subpath", "ENV_KEY")])
    (state,) = ecosystem.repository_states(
        [listing_component], EcosystemDirectories(None, None)
    )
    assert state.reachable is True and state.commit == REMOTE_SHA[:7]


@pytest.mark.parametrize(
    "probe_returncode, expected_status", [(0, "ok"), (128, "error")]
)
def test_git_access_probes_the_ecosystem_repositories_not_cloned(
    probe_returncode, expected_status, tmp_path, make_ecosystem
):
    ecosystem = make_ecosystem(FakeGitAccess(probe_returncode))
    ecosystem.register_repository("converters", "pdf-to-markdown")
    ecosystem.resolve_dirs = lambda deploy_dir=None: EcosystemDirectories(None, None)
    (row,) = click_group_git_access.ecosystem_probe_rows(FakeApplication(ecosystem))
    assert row[:2] == (expected_status, "pdf-to-markdown") and REMOTE_URL in row[2]


def test_git_access_does_not_probe_a_cloned_ecosystem_repository(
    tmp_path, make_ecosystem
):
    (tmp_path / "pdf-to-markdown").mkdir()
    ecosystem = make_ecosystem()
    ecosystem.repo_up_to_date = lambda path: True
    ecosystem.register_repository("converters", "pdf-to-markdown")
    ecosystem.resolve_dirs = lambda deploy_dir=None: EcosystemDirectories(
        tmp_path, None
    )
    assert click_group_git_access.ecosystem_probe_rows(FakeApplication(ecosystem)) == []


class FakeImageGitAccess(FakeGitAccess):
    """The HEAD of every remote is REMOTE_SHA."""


@pytest.mark.parametrize(
    "used_commits, expected",
    [
        ([REMOTE_SHA], True),
        ([REMOTE_SHA, LOCAL_SHA], False),
        ([REMOTE_SHA + "-dirty"], False),
        ([], None),
    ],
)
def test_used_commits_replace_the_clone_comparison(
    used_commits, expected, make_ecosystem, tmp_path
):
    ecosystem = make_ecosystem(FakeImageGitAccess())
    ecosystem.repo_up_to_date = lambda path: pytest.fail("the clone is not compared")
    directories = EcosystemDirectories(None, None)
    state = ecosystem.repository_state(
        "pdf-to-markdown", directories, used_commits=used_commits
    )
    assert state.up_to_date is expected


def test_used_commits_replace_the_clone_comparison_of_a_cloned_repository(
    make_ecosystem, tmp_path
):
    (tmp_path / "pdf-to-markdown").mkdir()
    ecosystem = make_ecosystem(FakeImageGitAccess())
    ecosystem.repo_up_to_date = lambda path: True
    state = ecosystem.repository_state(
        "pdf-to-markdown",
        EcosystemDirectories(tmp_path, None),
        used_commits=[LOCAL_SHA],
    )
    assert state.up_to_date is False
    assert state.location.is_local


def test_unreachable_remote_leaves_the_alignment_unknown(make_ecosystem):
    ecosystem = make_ecosystem(FakeGitAccess(probe_returncode=128))
    state = ecosystem.repository_state(
        "pdf-to-markdown", EcosystemDirectories(None, None), used_commits=[LOCAL_SHA]
    )
    assert state.up_to_date is None


def test_only_the_active_components_say_which_commits_they_use(make_ecosystem):
    ecosystem = make_ecosystem()
    ecosystem.register_repository(
        "convert", "pdf-to-markdown", used_commits=lambda: ["first"]
    )
    ecosystem.register_repository(
        "converters", "pdf-to-markdown", used_commits=lambda: ["second"]
    )
    assert ecosystem.used_commits("pdf-to-markdown", ["convert"]) == ["first"]
    assert ecosystem.used_commits("pdf-to-markdown", ["convert", "converters"]) == [
        "first",
        "second",
    ]
    assert ecosystem.used_commits("pdf-to-markdown", ["other"]) is None


@pytest.mark.parametrize(
    "document_commits, expected",
    [
        ([REMOTE_SHA], True),
        ([LOCAL_SHA], False),
        ([], None),
    ],
)
def test_document_image_alignment_with_the_remote_head(
    document_commits, expected, make_ecosystem
):
    ecosystem = make_ecosystem(FakeImageGitAccess())
    ecosystem.register_document_images("convert", lambda name: document_commits)
    assert ecosystem.offers_document_images(["convert"])
    assert not ecosystem.offers_document_images(["other"])
    assert ecosystem.document_image_aligned(["convert"], "jejune_doc_X") is expected
    assert ecosystem.document_image_aligned(["other"], "jejune_doc_X") is None


@pytest.mark.parametrize("aligned", [True, False, None])
def test_image_cell_is_as_wide_as_its_header(aligned):
    cell = click_group_ecosystem._StatusTable.image_cell(aligned)
    assert len(click.unstyle(cell)) == len(
        click_group_ecosystem._StatusTable.IMAGE_HEADER
    )


def test_documents_table_rule_spans_the_image_column():
    table = click_group_ecosystem._StatusTable
    header = click.unstyle(
        table.header("Document", "Manifest", "Repository", 10, 12, 7, True)
    )
    rule = table.rule(10, "Manifest", 12, 7, True)
    assert header.endswith(f"Commit   {table.IMAGE_HEADER}")
    assert len(rule) - 2 == len(header) - 2


def test_dirty_clone_is_not_up_to_date_and_its_commit_is_flagged(
    monkeypatch, make_ecosystem
):
    monkeypatch.setattr(
        ConverterCommits, "has_uncommitted_changes", staticmethod(lambda path: True)
    )
    ecosystem = make_ecosystem()
    assert ecosystem.repo_up_to_date("clone") is False
    assert ecosystem.short_head("clone") == (
        LOCAL_SHA[: ecosystem.SHORT_SHA_LENGTH] + ConverterCommits.DIRTY_SUFFIX
    )
