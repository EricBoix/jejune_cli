# jejune_cli<!-- omit in toc -->

## Table of content<!-- omit in toc -->

- [Introduction](#introduction)
- [Installing jejune\_cli](#installing-jejune_cli)
- [Single-document commands](#single-document-commands)
- [Collection-level commands](#collection-level-commands)
- [Notes and warnings](#notes-and-warnings)

## Introduction

`jejune_cli` addresses the jejuneness workflow through seven object-oriented command groups,
split into two scopes:

**Single-document** — operate on one `jj_doc_*` repository at a time:

```text
jejune env    <action>   # manage the local .jejune/ environment
jejune neo4j  <action>   # manage the Neo4j instance
jejune graph  <action>   # build and export the knowledge graph
```

**Collection-level** — operate across a catalog of repositories:

```text
jejune catalog          <action>   # manage the document catalog
jejune deployment       <action>   # manage deployments
jejune pdf-to-markdown  <action>   # test the pipeline across the catalog
```

Run `jejune doctor` at any time to see the health of your workspace.

### Pipeline summary

| Step | Command | Docker Image | Input | Output |
| ---- | ------- | ------------ | ----- | ------ |
| 1a. PDF to Markdown | (external: `jj_doc_some_book`) | — | PDF | `.md` + `.json` |
| 1b. Launch Neo4j | `jejune neo4j start` | `jejune:neo4j_docker` (built from [`jejune_neo4j_docker`](https://github.com/EricBoix/jejune_neo4j_docker)) | — | Neo4j server |
| 2. Markdown to Neo4j | `jejune graph extract` | `jejune:extract_knowledge_graph` (built from [`jejune_extract_knowledge_graph`](https://github.com/EricBoix/jejune_extract_knowledge_graph)) | `.md` + `.json` | Neo4j DB |
| 3. Neo4j to RDF | `jejune neo4j dump-turtle` | `jejune:jj_neo4j_to_rdf_ttl` (built from [`jj_neo4j_to_rdf_ttl`](https://github.com/EricBoix/jj_neo4j_to_rdf_ttl)) | Neo4j DB | `.ttl` |
| 4. Stop Neo4j | `jejune neo4j stop` | — | — | — |

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

## Single-document commands

### Set up the environment

Run `jejune env init` once in the repository where you intend to use `jejune`.
It writes scaffold files into a `.jejune/` directory and adds `.jejune` to `.gitignore`:

```bash
jejune env init
# edit .jejune/env-secrets with your credentials
```

Variables to set in `.jejune/env-secrets`:

| Variable | Required by | Purpose |
| -------- | ----------- | ------- |
| `NEO4J_PASSWORD` | all Neo4j commands | Database password |
| `LLM_MODEL_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` | `jejune graph extract` | LLM server |
| `JJ_ROOT_DIR` | catalog & deployment commands | Absolute path to the local directory holding all side-by-side `jj_*` clones |

**Scaffold files written by `jejune env init` into `.jejune/`:**

| File | Role |
| ---- | ---- |
| `.jejune/catalog.yaml` | Lists known `jj_doc_*` repositories; used by `catalog check` and `pdf-to-markdown test` |
| `.jejune/env-config` | Non-secret defaults (`NEO4J_PORT`, `NEO4J_URI`, `NEO4J_USERNAME`) |
| `.jejune/env-secrets` | Created by `init`; fill in credentials and `JJ_ROOT_DIR`; gitignored via `.jejune` |

```bash
jejune doctor                          # overall workspace health check

jejune env init                        # write .jejune/ scaffold files (run once per repo)
jejune env check                       # check env vars by use-case group (neo4j, llm, workspace)
```

### Neo4j commands

```bash
jejune neo4j start          # launch the Neo4j container
jejune neo4j stop           # stop the Neo4j container
jejune neo4j dump           # dump the Neo4j database to a file
jejune neo4j restore        # restore the Neo4j database from a dump
jejune neo4j dump-turtle    # export Neo4j → RDF/Turtle
```

### Graph commands

```bash
jejune graph extract        # run Markdown → Neo4j extraction (requires LLM)
```

---

## Collection-level commands

### Catalog commands

```bash
jejune catalog check                   # verify .jejune/catalog.yaml against GitHub visibility and local clones
jejune catalog sync                    # report public jj_doc_* repos missing from .jejune/catalog.yaml
jejune catalog sync --add              # append missing public repos to .jejune/catalog.yaml
jejune catalog check-deployment <path> # validate a deployment directory against .jejune/catalog.yaml
```

### Deployment commands

A *deployment* is a named configuration stored in the separate private `jj_deployments`
repository. It declares which `jj_doc_*` repositories are active and how to locate them
locally. This separation keeps private repository names out of any public repository.
See [`Doc/MarkdownRegistryDesignNotes.md`](./Doc/MarkdownRegistryDesignNotes.md) for the
full design rationale.

`JJ_ROOT_DIR` must be set to the absolute path of the local directory holding all
side-by-side `jj_*` clones (e.g. `/Users/you/workspace/`). It is machine-specific and
must not be committed.

```bash
# Clone or create the jj_deployments private repo
git clone git@github.com:EricBoix/jj_deployments.git   # or: git init jj_deployments

# Create a new deployment directory from scaffold files
jejune deployment configure jj_deployments my_deployment
```

This creates `jj_deployments/deploy_my_deployment/` containing:

| File | Committed | Purpose |
| ---- | --------- | ------- |
| `catalog.yaml` | yes | Active `jj_doc_*` repositories for this deployment |
| `deployment.env` | yes | Non-secret config (`JJ_CATALOG`, etc.) |
| `secrets.env` | **no** (gitignored) | `JJ_ROOT_DIR` and per-developer credentials |

Edit `catalog.yaml` (add private repos, remove unwanted ones), fill in `secrets.env`, then commit:

```bash
git -C jj_deployments add deploy_my_deployment/catalog.yaml \
                            deploy_my_deployment/deployment.env \
                            .gitignore
git -C jj_deployments commit -m "Add deploy_my_deployment deployment"
```

**Source a deployment before running collection-level commands:**

```bash
cd jj_deployments/deploy_my_deployment
source deployment.env
source secrets.env      # local only, never committed
```

```bash
jejune deployment configure <deployments-dir> <name>   # create a new deployment from scaffolds
jejune deployment list <deployments-dir>               # list available deployments
```

### pdf-to-markdown commands

```bash
jejune pdf-to-markdown test                            # run Convert/test_main.py for each repo in the catalog
jejune pdf-to-markdown test \
  --catalog /path/to/jj_deployments/deploy_my_deployment/catalog.yaml \
  --root-dir /Users/you/workspace/                    # test against a specific deployment catalog
```

---

## Notes and warnings

### Concerning neo4j database

- **WARNING**: the username/password given to the neo4j database are only **initial** values
  (valid when starting the database for the first time). Once the neo4j db has been
  initialized those values are "burned" into the `database` files.
- There are many caveats with the name of a neo4j dump:
  - the [neo4j-admin](https://neo4j.com/docs/operations-manual/current/neo4j-admin-neo4j-cli/)
    utility does not allow providing the filename of the dump.
  - when restoring a dump, the provided database name must have a length between 1 and 63 characters.
  - a neo4j username/password are burnt into the dump and cannot be overwritten. When dumping
    a neo4j DB one must keep the (dump, username, password) triplet.
