from types import SimpleNamespace

from jejune_cli.component_ext_server_git import CompServerGit


def make_git_server(*provider_urls):
    git_server = CompServerGit(
        network=SimpleNamespace(name="network"),
        git_command=SimpleNamespace(name="git-command"),
    )
    for index, urls in enumerate(provider_urls):
        git_server.set_runtime_dependency(
            f"provider{index}", SimpleNamespace(repository_urls=lambda urls=urls: urls)
        )
    return git_server


def test_hosts_are_distinct_and_exclude_the_default_host():
    git_server = make_git_server([])
    default_url = f"{git_server.repo_root_dir()}/a.git"
    git_server = make_git_server(
        [default_url, "https://example.org/team/b.git"],
        ["https://example.org/team/c.git", "http://other.net:8080/d.git"],
    )
    assert git_server.hosts() == [("example.org", 443), ("other.net", 8080)]


def test_unreachable_host_is_reported(monkeypatch):
    git_server = make_git_server(["https://nonexistent.invalid/x.git"])
    monkeypatch.setattr(
        CompServerGit, "check_default_host", lambda self, timeout: ("ok", "")
    )
    status, message = git_server.check(timeout=1)
    assert status == "error"
    assert "nonexistent.invalid" in message
