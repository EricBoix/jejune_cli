# jejune_cli<!-- omit in toc -->

## Table of content<!-- omit in toc -->

- [Introduction](#introduction)
- [Stage 1 — Configure: set up the workspace](#stage-1--configure-set-up-the-workspace)
  - [Install](#install)
  - [Configure the environment](#configure-the-environment)
  - [Configure commands](#configure-commands)
- [Stage 2 — Build: run the treatment pipeline](#stage-2--build-run-the-treatment-pipeline)
  - [Build commands](#build-commands)
- [Stage 3 — Exploit: deploy and browse results](#stage-3--exploit-deploy-and-browse-results)
  - [Set up a deployment](#set-up-a-deployment)
  - [Exploit commands](#exploit-commands)
- [Notes and warnings](#notes-and-warnings)

## Introduction

`jejune_cli` addresses three clearly distinct stages of the jejuneness workflow,
unified under the `jejune` command-line interface:

```text
jejune doctor                        # overall workspace health check (run this first)
jejune configure <action>            # Stage 1 — verify workspace coherence
jejune build     <action>            # Stage 2 — run the treatment pipeline
jejune deploy    <action>            # Stage 3 — manage and launch deployments
```

`jejune doctor` (inspired by `brew doctor`) runs all Stage 1 checks in sequence and
produces a pass/fail summary. It is the recommended first command to run on a fresh
checkout or after any configuration change.

**Stage 1 — Configure.** Verify that the local workspace is correctly set up: environment
variables are defined, `catalog-reference.yaml` is coherent with what is actually hosted on
GitHub and cloned locally, and deployment configurations are valid. This stage has no
side-effects on data; it only reads and reports.

**Stage 2 — Build.** Run the data-processing pipeline that turns source documents (PDFs
in `jj_doc_*` repositories) into a knowledge graph (RDF/Turtle file). This is a
per-document, per-developer operation that requires a running Neo4j instance and access
to an LLM server. The pipeline is implemented as a chain of Docker container invocations.

**Stage 3 — Exploit.** Configure and launch the downstream tools (`jj_vis_net_viewer`,
`jj_markdown_browser`) that consume the Turtle files produced by Stage 2. This stage
revolves around *deployments*: named configurations that declare which `jj_doc_*`
repositories are active and where they are cloned locally. Multiple deployments can coexist
(e.g. a public-only deployment and a full deployment that includes private repositories).

Each stage has **separate configuration concerns**: Stage 2 needs Neo4j and LLM credentials;
Stage 3 needs a catalog of repositories and local paths. Only Stage 3 involves the
`jj_deployments` private repository and the deployment catalog scheme.

### Pipeline Summary (Stage 2)

| Step | `jejune build` command | Docker Image | Input | Output |
| ---- | ---------------------- | ------------ | ----- | ------ |
| 1a. PDF to Markdown | (external: `jj_doc_some_book`) | — | PDF | `.md` + `.json` |
| 1b. Launch Neo4j | `neo4j-start` | `jejuneness:jj_neo4j_docker` (built from [`jj_neo4j_docker`](https://github.com/EricBoix/jj_neo4j_docker)) | — | Neo4j server |
| 2. Markdown to Neo4j | `extract` | `jejuneness:jj_build_knowledge_graph` (built from [`jj_build_knowledge_graph`](https://github.com/EricBoix/jj_build_knowledge_graph)) | `.md` + `.json` | Neo4j DB |
| 3. Neo4j to RDF | `dump-turtle` | `jejuneness:jj_neo4j_to_rdf_ttl` (built from [`jj_neo4j_to_rdf_ttl`](https://github.com/EricBoix/jj_neo4j_to_rdf_ttl)) | Neo4j DB | `.ttl` |
| 4. Stop Neo4j | `neo4j-stop` | — | — | — |

---

## Stage 1 — Configure: set up the workspace

### Install

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

### Configure the environment

Run `jejune configure init` once in the repository where you intend to use `jejune`.
It writes scaffold files into a `.jejune/` directory and adds `.jejune` to `.gitignore`:

```bash
jejune configure init
# edit .jejune/env-secrets with your credentials
```

Variables to set in `.jejune/env-secrets`:

| Variable | Required by | Purpose |
| -------- | ----------- | ------- |
| `NEO4J_PASSWORD` | all Neo4j commands | Database password |
| `LLM_MODEL_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` | `jejune build extract` | LLM server |
| `JJ_ROOT_DIR` | Stages 1 & 3 | Absolute path to the local directory holding all side-by-side `jj_*` clones |

### Configure commands

```bash
jejune doctor                               # run all checks below and report overall health

jejune configure init                       # write .jejune/ scaffold files (run once per repo)
jejune configure check-env                  # verify all variables from .jejune/env-secrets are set and non-placeholder
jejune configure check-catalog              # verify .jejune/catalog-reference.yaml against GitHub visibility and local clones
jejune configure sync-catalog               # report public jj_doc_* repos missing from .jejune/catalog-reference.yaml
jejune configure check-deployment <path>    # validate a deployment catalog against .jejune/catalog-reference.yaml
```

---

## Stage 2 — Build: run the treatment pipeline

### Build commands

```bash
jejune build neo4j-start        # launch the Neo4j container
jejune build extract            # run Markdown → Neo4j extraction (requires LLM)
jejune build dump-turtle        # export Neo4j → RDF/Turtle
jejune build neo4j-stop         # stop the Neo4j container
jejune build neo4j-dump         # dump the Neo4j database to a file
jejune build neo4j-restore      # restore the Neo4j database from a dump
jejune build test               # run Convert/test_main.py for each repo in the catalog
```

---

## Stage 3 — Exploit: deploy and browse results

A *deployment* is a named configuration stored in the separate private `jj_deployments`
repository. It declares which `jj_doc_*` repositories are active and how to locate them
locally. This separation keeps private repository names and credentials out of any public
repository. See [`Doc/MarkdownRegistryDesignNotes.md`](./Doc/MarkdownRegistryDesignNotes.md)
for the full design rationale.

`jejune configure check-deployment <path>` (Stage 1) can validate a deployment catalog before use.

**Scaffold files written by `jejune configure init` into `.jejune/`:**

| File | Role |
| ---- | ---- |
| `.jejune/catalog-reference.yaml` | Lists all public `jj_doc_*` repositories; scaffold only, never read at runtime |
| `.jejune/env-config` | Non-secret defaults (`NEO4J_PORT`, `NEO4J_URI`, `NEO4J_USERNAME`) |
| `.jejune/env-secrets` | Created by `init`; fill in credentials and `JJ_ROOT_DIR`; gitignored via `.jejune` |

`JJ_ROOT_DIR` must be set to the absolute path of the local directory holding all
side-by-side `jj_*` clones (e.g. `/Users/you/workspace/`). It is machine-specific and
must not be committed.

### Set up a deployment

```bash
# Clone or create the jj_deployments private repo alongside jejune_cli
git clone git@github.com:EricBoix/jj_deployments.git   # or: git init jj_deployments

# Bootstrap a new deployment directory from the scaffolds
jejune deploy bootstrap jj_deployments my_deployment
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

**Source a deployment before running exploit commands:**

```bash
cd jj_deployments/deploy_my_deployment
source deployment.env
source secrets.env      # local only, never committed
```

**Run tests against a deployment catalog:**

```bash
jejune build test \
  --catalog /path/to/jj_deployments/deploy_my_deployment/catalog.yaml \
  --root-dir /Users/you/workspace/
```

### Exploit commands

```bash
jejune deploy bootstrap <deployments-dir> <name>    # create a new deployment from scaffolds
jejune deploy list                                  # list available deployments
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
