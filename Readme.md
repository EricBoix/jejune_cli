# jejune_cli<!-- omit in toc -->

## Table of content<!-- omit in toc -->

- [Introduction](#introduction)
- [Roles](#roles)
- [Installing jejune\_cli](#installing-jejune_cli)
- [Commands for all roles](#commands-for-all-roles)
- [Doc-steward commands](#doc-steward-commands)
- [Catalog Curator commands](#catalog-curator-commands)
- [Deployer commands](#deployer-commands)
- [Notes and warnings](#notes-and-warnings)

## Introduction

`jejune_cli` groups commands by **role** — the active role is inferred from the
current directory, or forced via the `JEJUNE_ROLE` env var.
The `--help` output and `jejune doctor` checks are filtered to the detected role.

```text
# For all roles
jejune doctor            # overall workspace health check
jejune init              # role-aware workspace initialization
jejune configuration     # manage the .jejune/ configuration
jejune role              # show or list roles
jejune containers        # manage jejune-managed Docker containers

# Doc-steward  (inferred from .jejune/)
jejune neo4j             # manage the Neo4j instance
jejune llm               # manage the LLM inference server
jejune llm-observability # manage the LLM observability backend
jejune graph             # build and export the knowledge graph
jejune convert           # convert documents via Docker

# Catalog Curator  (inferred from full-catalog.yaml)
jejune pdf-to-markdown   # test the pipeline across the catalog

# Deployer  (inferred from docker-compose.yml)
jejune deployment        # manage deployments
```

### Pipeline summary

| Step | Command | Docker Image | Input | Output |
| ---- | ------- | ------------ | ----- | ------ |
| 1a. PDF to Markdown | (external: `jejune_doc_some_book`) | — | PDF | `.md` + `.json` |
| 1b. Launch Neo4j | `jejune neo4j start` | `jejune:neo4j_docker` (built from [`jejune_neo4j_docker`](https://github.com/EricBoix/jejune_neo4j_docker)) | — | Neo4j server |
| 2. Markdown to Neo4j | `jejune graph extract` | `jejune:extract_knowledge_graph` (built from [`jejune_extract_knowledge_graph`](https://github.com/EricBoix/jejune_extract_knowledge_graph)) | `.md` + `.json` | Neo4j DB |
| 3. Neo4j to RDF | `jejune neo4j dump-turtle` | `jejune:jj_neo4j_to_rdf_ttl` (built from [`jj_neo4j_to_rdf_ttl`](https://github.com/EricBoix/jj_neo4j_to_rdf_ttl)) | Neo4j DB | `.ttl` |
| 4. Stop Neo4j | `jejune neo4j stop` | — | — | — |

---

## Roles

| Role | Detected when | Visible commands |
| ---- | ------------- | ---------------- |
| `doc-steward` | `.jejune/` directory exists in cwd | neo4j, llm, llm-observability, graph, convert |
| `catalog-curator` | `full-catalog.yaml` exists in cwd | pdf-to-markdown |
| `deployer` | `docker-compose.yml` exists in cwd | deployment |
| *(none)* | no indicator found | all commands |

Override at any time:

```bash
JEJUNE_ROLE=doc-steward jejune --help
```

```bash
jejune role          # show detected role and reason
jejune role list     # list all known roles
```

---

## Installing jejune_cli

**One-shot (no clone needed):**

```bash
uvx --from git+https://github.com/EricBoix/jejune_cli jejune doctor
```

**Persistent tool install:**

```bash
uv tool install git+https://github.com/EricBoix/jejune_cli
jejune doctor
```

**Development install (editable):**

```bash
git clone https://github.com/EricBoix/jejune_cli.git
cd jejune_cli
uv sync          # creates .venv and installs jejune-cli in editable mode
uv run jejune doctor
```

---

## Commands for all roles

### Initialize and configure

Run `jejune init` once in the repository where you intend to use `jejune`.
Its behaviour is role-aware:

| Detected role | What `jejune init` does |
| ------------- | ----------------------- |
| `doc-steward` (or none) | writes scaffold files into `.jejune/` and adds `.jejune` to `.gitignore` |
| `deployer` | scaffolds a deployment directory named `NAME` (requires `NAME` argument) |
| `catalog-curator` | not yet implemented |

```bash
jejune init              # role-aware initialization
jejune init my_deploy    # deployer role: create deploy_my_deploy/
```

Edit `.jejune/env-secrets` after `doc-steward` init:

| Variable | Required by | Purpose |
| -------- | ----------- | ------- |
| `NEO4J_PASSWORD` | all Neo4j commands | Database password |
| `LLM_MODEL_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` | `jejune graph extract` | LLM server |
| `JEJUNE_ROOT_DIR` | catalog & deployment commands | Absolute path to the local directory holding all side-by-side `jejune_*` clones |

**Scaffold files written by `jejune init` into `.jejune/`:**

| File | Role |
| ---- | ---- |
| `.jejune/catalog.yaml` | Lists known `jejune_doc_*` repositories; used by `pdf-to-markdown test` |
| `.jejune/env-config` | Non-secret defaults (`NEO4J_PORT`, `NEO4J_URI`, `NEO4J_USERNAME`) |
| `.jejune/env-secrets` | Created by `init`; fill in credentials and `JEJUNE_ROOT_DIR`; gitignored via `.jejune` |

```bash
jejune doctor                    # overall workspace health check
jejune configuration init        # write .jejune/ scaffold files (same as `jejune init` for doc-steward)
jejune configuration check-config # check env vars by use-case group (neo4j, llm, workspace)
```

---

## Doc-steward commands

Doc-steward commands operate on one `jejune_doc_*` repository at a time.
They are shown in `--help` when a `.jejune/` directory is detected in the
current directory.

### Neo4j commands

```bash
jejune neo4j start          # launch the Neo4j container
jejune neo4j stop           # stop the Neo4j container
jejune neo4j stats          # show Neo4j node and relationship counts
jejune neo4j dump           # dump the Neo4j database to a file
jejune neo4j restore        # restore the Neo4j database from a dump
jejune neo4j dump-turtle    # export Neo4j → RDF/Turtle
jejune neo4j delete         # delete the Neo4j container and its data
```

### LLM commands

```bash
jejune llm status           # show LLM server availability
```

### LLM observability commands

```bash
jejune llm-observability start   # launch the observability backend
jejune llm-observability stop    # stop the observability backend
```

### Graph commands

```bash
jejune graph extract        # run Markdown → Neo4j extraction (requires LLM + Neo4j)
jejune graph view           # visualize a Turtle file in the browser
```

### Convert commands

`jejune convert` only appears in `--help` when `CONVERT_DOC_DIR` is set and
the `DockerContext/` subdirectory exists.

```bash
jejune convert build        # build the converter Docker image
jejune convert run          # run the converter container
```

---

## Catalog Curator commands

Catalog Curator commands operate across a catalog of repositories.
They are shown in `--help` when `full-catalog.yaml` is detected in the current directory.

### pdf-to-markdown commands

```bash
jejune pdf-to-markdown test                            # run Convert/test_main.py for each repo in the catalog
jejune pdf-to-markdown test \
  --catalog /path/to/jejune_deployments/deploy_my_deployment/catalog.yaml \
  --root-dir /Users/you/workspace/                    # test against a specific deployment catalog
```

---

## Deployer commands

Deployer commands are shown in `--help` when `docker-compose.yml` is detected
in the current directory.

A *deployment* is a named configuration stored in a separate directory
(possibly part of a private `jejune_deployments` repository). It declares which
`jejune_doc_*` repositories are active and how to locate them locally. This
separation keeps private repository names out of any public repository.
See [`Doc/MarkdownRegistryDesignNotes.md`](./Doc/MarkdownRegistryDesignNotes.md)
for the full design rationale.

`JEJUNE_ROOT_DIR` must be set to the absolute path of the local directory
holding all side-by-side `jejune_*` clones (e.g. `/Users/you/workspace/`). It is
machine-specific and must not be committed.

```bash
# Clone or create the jejune_deployments private repo
git clone git@github.com:EricBoix/jejune_deployments.git   # or: git init jejune_deployments

# Create a new deployment directory from scaffold files
jejune deployment configure jejune_deployments my_deployment
```

This creates `jejune_deployments/deploy_my_deployment/` containing:

| File | Committed | Purpose |
| ---- | --------- | ------- |
| `catalog.yaml` | yes | Active `jejune_doc_*` repositories for this deployment |
| `deployment.env` | yes | Non-secret config (`JJ_CATALOG`, etc.) |
| `secrets.env` | **no** (gitignored) | `JEJUNE_ROOT_DIR` and per-developer credentials |

Edit `catalog.yaml` (add private repos, remove unwanted ones), fill in
`secrets.env`, then commit:

```bash
git -C jejune_deployments add deploy_my_deployment/catalog.yaml \
                            deploy_my_deployment/deployment.env \
                            .gitignore
git -C jejune_deployments commit -m "Add deploy_my_deployment deployment"
```

**Source a deployment before running deployer commands:**

```bash
cd jejune_deployments/deploy_my_deployment
source deployment.env
source secrets.env      # local only, never committed
```

```bash
jejune deployment configure <deployments-dir> <name>   # create a new deployment from scaffolds
jejune deployment list <deployments-dir>               # list available deployments
```

---

## Notes and warnings

### Concerning neo4j database

- **WARNING**: the username/password given to the neo4j database are only
  **initial** values (valid when starting the database for the first time).
  Once the neo4j db has been initialized those values are "burned" into the
  `database` files.
- There are many caveats with the name of a neo4j dump:
  - the [neo4j-admin](https://neo4j.com/docs/operations-manual/current/neo4j-admin-neo4j-cli/)
    utility does not allow providing the filename of the dump.
  - when restoring a dump, the provided database name must have a length between
    1 and 63 characters.
  - a neo4j username/password are burnt into the dump and cannot be overwritten.
    When dumping a neo4j DB one must keep the (dump, username, password) triplet.
