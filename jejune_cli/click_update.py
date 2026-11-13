"""``jejune update`` — reinstall jejune from where it was installed, then its plugins."""

import importlib.metadata
import json
import subprocess

import click


class JejuneUpdater:
    """Reinstalls the jejune uv tool from its recorded install origin."""

    DISTRIBUTION_NAME = "jejune-cli"
    DIRECT_URL_FILE = "direct_url.json"

    def install_specification(self) -> str:
        """Return the ``git+<url>[@<revision>]`` the tool was originally installed from.

        Read from the PEP 610 ``direct_url.json`` that uv writes in the dist-info.
        """
        raw_direct_url = importlib.metadata.distribution(
            self.DISTRIBUTION_NAME
        ).read_text(self.DIRECT_URL_FILE)
        if raw_direct_url is None:
            raise click.ClickException(
                f"No {self.DIRECT_URL_FILE} found for {self.DISTRIBUTION_NAME}: "
                "cannot tell where jejune was installed from."
            )
        direct_url = json.loads(raw_direct_url)
        if direct_url.get("dir_info", {}).get("editable"):
            raise click.ClickException(
                "Editable install: update the source directory with `git pull` instead."
            )
        vcs_info = direct_url.get("vcs_info", {})
        if vcs_info.get("vcs") != "git":
            raise click.ClickException(
                f"Unsupported install origin in {self.DIRECT_URL_FILE}: {direct_url}"
            )
        specification = f"git+{direct_url['url']}"
        requested_revision = vcs_info.get("requested_revision")
        if requested_revision:
            specification += f"@{requested_revision}"
        return specification

    def reinstall_tool(self) -> None:
        command = [
            "uv",
            "tool",
            "install",
            "--reinstall",
            "--refresh",
            self.install_specification(),
        ]
        if subprocess.run(command).returncode != 0:
            raise click.ClickException("Reinstalling the jejune tool failed.")

    def install_plugin_packages(self) -> None:
        # New process: the running one holds the replaced code and environment.
        if subprocess.run(["jejune", "plugin-packages", "install"]).returncode != 0:
            raise click.ClickException("Installing the plugin packages failed.")


@click.command(
    "update", short_help="Reinstall jejune from its install origin, then its plugins."
)
@click.option(
    "--no-plugins",
    is_flag=True,
    default=False,
    help="Skip `jejune plugin-packages install` after reinstalling jejune.",
)
def update_cmd(no_plugins: bool) -> None:
    """Reinstall jejune (uv tool install --reinstall --refresh) from the origin it
    was installed from, then run `jejune plugin-packages install`."""
    updater = JejuneUpdater()
    updater.reinstall_tool()
    if not no_plugins:
        updater.install_plugin_packages()
