"""neo4j containerized component."""
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from .component_containerized import cont_comp
from .configuration import configuration


class comp_neo4j(cont_comp):
    def __init__(self) -> None:
        git_server = type(self).registry.get("git-server")
        super().__init__(
            name="neo4j",
            image_name="jejune:neo4j",
            build_context=git_server.remote_git_url("jejune_neo4j_docker"),
            dependencies=[git_server, type(self).registry.get("docker-hub-server")],
            hint="run `jejune neo4j start --help`",
            configuration=configuration("edit .jejune/env-secrets or .jejune/env-config", env_vars=["NEO4J_PASSWORD"])
        )
        type(self).registry.add(self)

    def launch_container(self, data_dir: Path, port: str, credentials: str) -> None:
        """Build, start, and wait for the Neo4j container to be ready."""
        self.build()
        (data_dir / "database").mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "docker", "run", "--rm", "--detach",
                "--name", self.container_name,
                "--publish", "7474:7474",
                "--publish", f"{port}:7687",
                "--env", f"NEO4J_AUTH={credentials}",
                "-v", f"{data_dir}/database:/data",
                self.image_name,
            ]
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)
        while not self.is_running()[0]:
            time.sleep(0.5)
        time.sleep(5)
        self.register(port=int(port))

    def resolve_port_credentials(
        self, port: str | None, credentials: str | None
    ) -> tuple[str, str]:
        """Resolve port and credentials from explicit args or environment variables."""
        if port is None:
            port = os.environ.get("NEO4J_PORT", "7687")
        if credentials is None:
            user = os.environ.get("NEO4J_USERNAME")
            password = os.environ.get("NEO4J_PASSWORD")
            if not user or not password:
                raise ValueError(
                    "Provide --credentials USER/PASSWORD or set NEO4J_USERNAME and NEO4J_PASSWORD."
                )
            credentials = f"{user}/{password}"
        return port, credentials

    def wipe_database(self, database_dir: Path) -> None:
        """Remove the Neo4j database directory entirely."""
        import shutil
        shutil.rmtree(database_dir, ignore_errors=True)

    def restore(self, results_dir: Path, dump_filename: str) -> None:
        """Restore the Neo4j database from results_dir/backups/dump_filename."""
        import shutil

        database_dir = results_dir / "database"
        backups_dir = results_dir / "backups"
        dump_path = backups_dir / dump_filename

        if not dump_path.exists():
            raise RuntimeError(f"Dump file not found: {dump_path}")
        running, _ = self.is_running()
        if running:
            raise RuntimeError("neo4j is running — stop it first with `jejune neo4j stop`")

        self.wipe_database(database_dir)

        # neo4j-admin load expects the source file to be named neo4j.dump
        shutil.copy2(dump_path, backups_dir / "neo4j.dump")

        result = subprocess.run(
            [
                "docker", "run", "--interactive", "--tty", "--rm",
                f"--volume={database_dir}:/data",
                f"--volume={backups_dir}:/backups",
                "neo4j/neo4j-admin", "neo4j-admin", "database", "load", "neo4j",
                "--from-path=/backups",
            ]
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    def dump(self, results_dir: Path, dump_filename: str) -> Path:
        """Dump the database to results_dir/backups/dump_filename; return the dump path."""
        database_dir = results_dir / "database"
        backups_dir = results_dir / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        running, _ = self.is_running()
        if running:
            raise RuntimeError("neo4j is running — stop it first with `jejune neo4j stop`")
        existing = backups_dir / "neo4j.dump"
        if existing.exists():
            raise RuntimeError(f"{existing} already exists — remove it first")
        result = subprocess.run(
            [
                "docker", "run", "--interactive", "--tty", "--rm",
                f"--volume={database_dir}:/data",
                f"--volume={backups_dir}:/output",
                "neo4j/neo4j-admin", "neo4j-admin", "database", "dump", "neo4j",
                "--to-path=/output",
            ]
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)
        # neo4j-admin does not allow choosing the output filename; rename afterwards
        (backups_dir / "neo4j.dump").rename(backups_dir / dump_filename)
        return backups_dir / dump_filename

    def _neo4j_auth_token(self) -> str:
        user = os.environ.get("NEO4J_USERNAME", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "")
        return base64.b64encode(f"{user}:{password}".encode()).decode()

    def db_is_empty(self) -> bool:
        """Return True when the running Neo4j database has no nodes; True on any error."""
        running, _ = self.is_running()
        if not running:
            return True
        token = self._neo4j_auth_token()
        payload = json.dumps(
            {"statements": [{"statement": "MATCH (n) RETURN count(n) AS count"}]}
        ).encode()
        req = urllib.request.Request(
            "http://localhost:7474/db/neo4j/tx/commit",
            data=payload,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            return data["results"][0]["data"][0]["row"][0] == 0
        except Exception:
            return True

    def stats(self) -> tuple[int, list[tuple[str, int]], int, list[tuple[str, int]]]:
        """Fetch node/relationship counts from the running Neo4j HTTP API."""
        token = self._neo4j_auth_token()
        payload = json.dumps(
            {
                "statements": [
                    {"statement": "MATCH (n) RETURN count(n) AS count"},
                    {
                        "statement": "MATCH (n) UNWIND labels(n) AS label "
                        "RETURN label, count(*) AS count ORDER BY count DESC"
                    },
                    {"statement": "MATCH ()-[r]->() RETURN count(r) AS count"},
                    {
                        "statement": "MATCH ()-[r]->() "
                        "RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
                    },
                ]
            }
        ).encode()
        req = urllib.request.Request(
            "http://localhost:7474/db/neo4j/tx/commit",
            data=payload,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError as e:
            raise RuntimeError(f"could not reach Neo4j HTTP API: {e.reason}")
        if data.get("errors"):
            raise RuntimeError(f"Neo4j error: {data['errors'][0]['message']}")
        results = data["results"]
        total_nodes = results[0]["data"][0]["row"][0]
        nodes_by_label = [(r["row"][0], r["row"][1]) for r in results[1]["data"]]
        total_relationships = results[2]["data"][0]["row"][0]
        relationships_by_type = [(r["row"][0], r["row"][1]) for r in results[3]["data"]]
        return total_nodes, nodes_by_label, total_relationships, relationships_by_type

    def check(self) -> tuple[str, str]:
        cfg_status, *_ = self.configuration.check()
        running, msg = self.is_running()
        if running:
            return "ok", ""
        return ("warn" if cfg_status != "ok" else "error"), msg


neo4j_comp = comp_neo4j()
