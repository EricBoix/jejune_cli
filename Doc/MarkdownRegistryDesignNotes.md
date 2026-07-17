# Markdown Registry — Design Notes<!-- omit from toc -->

> **Historical note:** this design document was written when the codebase was at commit
> [`b809f17`](https://github.com/EricBoix/jj_workflow_shell/tree/b809f17967eb9e5b7c25fd0a9a55f2d12cd43475).
> Read it in that context — shell functions and file structures described here may have since
> been superseded by the `jejune` CLI.

## Table of contents<!-- omit from toc -->

- [Context and initial use-case](#context-and-initial-use-case)
- [Design exploration](#design-exploration)
- [Description of the retained solution](#description-of-the-retained-solution)

## Context and initial use-case

The jejuneness project processes a set of source documents (books, articles, talk transcripts)
collected in dedicated `jj_doc_*` repositories. The global treatment pipeline goes:

1. Each `jj_doc_*` repo contains the source material and a `Convert/` subdirectory with
   document-specific preprocessing scripts.
2. The `jj_workflow_shell` pipeline (a chain of Docker container invocations) processes each
   `jj_doc_*` repo and writes a knowledge graph as an RDF/Turtle file into the repo's
   `result_data/` subdirectory.

The resulting set of RDF/Turtle files are consumed by downstream tools e.g.

1. `jj_vis_network_viewer` that does resulting knowledge graph visualisations
2. `jj_markdown_browser` that displays the original source passages (markdown snippets at a
   specific line range) when the user navigates to a node in the knowledge graph.

### Minimum requirement

This leads to three transversal problems that span all components and cannot be solved locally within any single repo:

1. **Registry** — a canonical, machine-readable list of all `jj_doc_*` repositories, shared
   by `jj_workflow_shell` (pipeline orchestration), `jj_vis_net_viewer` (visualisation), and
   `jj_markdown_browser` (source display).

2. **Source reference URI** — a knowledge-graph node must carry enough information to trace
   back unambiguously to its origin: which repository, which file within that repository, and
   which line range.

3. **URI resolution** — `jj_markdown_browser` operates inside a Docker container and addresses
   files by absolute container paths (`/config/...`). It must be able to turn a source
   reference URI into such a path at runtime.

### Additional requirements

Raised during elaboration:

1. **Multiple simultaneous deployments** — e.g. a *public* deployment (only open-source
   `jj_doc_*` repos) and a *full* deployment (public + private repos) may coexist on the same
   machine or be used by different team members.

1. **Access control** — private `jj_doc_*` repository names must never appear in any
   publicly committed file.

1. **Team sharing** — deployment configurations must be shareable among authorized team
   members under version control.

1. **Secret isolation** — credentials (LLM API keys, Neo4j passwords, etc.) must not be
   committed, even to private repositories.

1. **Bootstrapping** — creating a new deployment must be a guided, low-friction operation.

## Design exploration

### Concerning the registry requirement: Solution A — static catalog and URI convention

A `catalog.yaml` file lists all `jj_doc_*` repositories. URI resolution is a pure string
transformation: no service needs to be running. `jj_markdown_browser`'s Docker `run` command
mounts each `jj_doc_*` output directory at a predictable container path derived from the repo
name.

### Concerning the registry requirement: Solution B — REST registry service

A `jj_doc_registry` REST API (hosted inside `jj_workflow_shell`) accepts registration calls
from the pipeline and answers resolution queries from `jj_markdown_browser`.

### Comparison of registry solutions

| Dimension | A — static catalog | B — REST registry |
| --------- | ------------------ | ----------------- |
| Runtime dependencies | None | Service must be running at pipeline time and at browse time |
| URI resolution | String transformation | HTTP round-trip |
| Offline use | Full | Blocked if service unreachable |
| Clone-path config | Per-machine `.env` | Centralized (registry stores paths set at registration time) |
| Adding a new `jj_doc_*` | Manual catalog edit | Automatic (`POST /register` from pipeline) |
| State richness | Repo list only | Can track run history, errors, versions |
| Implementation cost | ~50-line YAML + launcher script | REST API + persistence + lifecycle management |
| Failure blast radius | Parse error | Total outage |
| Fit for current scale (≤10 repos, 1 developer) | Ideal | Over-engineered |

**Decision: Solution A**, retaining the option to graduate to Solution B if scale or team
size grows significantly. The dynamic registration advantage of B can be partially recovered
in A by having the pipeline write a `catalog.local.yaml` (gitignored) that records resolved
local paths after each run.

### Concerning the handling multiple deployments requirement

Three sub-options were evaluated for managing per-deployment catalogs:

| Option | Mechanism | Verdict |
| ------ | --------- | ------- |
| Named catalog files in `jj_workflow_shell` | `catalog-public.yaml`, `catalog-full.yaml` selected via env var | Ruled out: private repo names would appear in a public repo |
| Two-level inheritance | Committed base + gitignored per-deployment overlay, merged at runtime | Viable but requires merge logic; overlay files are scattered |
| Dedicated `jj_deployments` repo | One subdirectory per deployment, each with its own complete `catalog.yaml` | **Retained**: self-contained, auditable, no merge logic, team-shareable under access control |

The `jj_deployments` repo must be **private** so that deployment catalogs listing private
`jj_doc_*` repos remain confidential.

**Role of `jj_workflow_shell/catalog-reference.yaml`** — this committed file lists all
*public* `jj_doc_*` repositories and serves exclusively as a scaffold when creating a new
deployment. It is never read by any tool at runtime. This follows the existing
`jj_workflow_shell/env-reference` pattern.

## Description of the retained solution

### Repositories involved

| Repository | Visibility | Role |
| ---------- | ---------- | ---- |
| `jj_workflow_shell` | public | Pipeline utilities; hosts `catalog-reference.yaml` and `env-reference` as deployment scaffolds |
| `jj_deployments` | **private** | One subdirectory per deployment; authoritative runtime catalogs and non-secret config |
| `jj_doc_*` | public or private | Source documents; `Convert/` preprocessing; `result_data/` Turtle output |
| `jj_markdown_browser` | public | Docker-based markdown viewer; reads deployment catalog to mount volumes |
| `jj_vis_net_viewer` | public | Turtle visualiser; reads deployment catalog |

### Directory structure

```text
<workspace>/                               # side-by-side clone convention
├── jj_workflow_shell/
│   ├── catalog-reference.yaml             # scaffold only — never read at runtime
│   ├── env-reference                      # existing secrets scaffold
│   └── Testing/
│       └── Makefile                       # reads JJ_CATALOG env var (fails fast if unset)
├── jj_deployments/                        # private repo
│   ├── .gitignore                         # **/secrets.env
│   ├── deploy_public/
│   │   ├── catalog.yaml                   # public repos only
│   │   ├── deployment.env                 # committed, non-secret config
│   │   └── secrets.env                    # gitignored
│   └── deploy_full/
│       ├── catalog.yaml                   # public + private repos
│       ├── deployment.env
│       └── secrets.env
└── jj_doc_*/
    ├── Convert/
    └── result_data/
```

### File roles and contents

**`jj_workflow_shell/catalog-reference.yaml`** — scaffold listing all public repos:

```yaml
# Reference catalog — copy to a jj_deployments/deploy_*/catalog.yaml and customise.
# This file is never read at runtime.
documents:
  - name: jj_doc_Collecting_Gold_Dust
    url: https://github.com/EricBoix/jj_doc_Collecting_Gold_Dust
    public: true
  - name: jj_doc_Zen_Flesh_Zen_Bones
    url: https://github.com/EricBoix/jj_doc_Zen_Flesh_Zen_Bones
    public: true
  # add new public jj_doc_* repos here as they are created
```

**`jj_deployments/deploy_AA/catalog.yaml`** — authoritative runtime catalog for that
deployment (private repos may be added freely since `jj_deployments` is private):

```yaml
documents:
  - name: jj_doc_Collecting_Gold_Dust
    url: https://github.com/EricBoix/jj_doc_Collecting_Gold_Dust
    public: true
  - name: jj_doc_Rob_Burbea               # private — only in deploy_full
    url: https://github.com/EricBoix/jj_doc_Rob_Burbea
    public: false
```

**`jj_deployments/deploy_AA/deployment.env`** — committed, non-secret deployment config:

```bash
JJ_CATALOG=./catalog.yaml
JJ_DOCS_ROOT=../../          # path to workspace root relative to this deploy dir
NEO4J_VERSION=5.x
```

**`jj_deployments/deploy_AA/secrets.env`** — gitignored, per-developer:

```bash
LLM_API_KEY=sk-...
NEO4J_PASSWORD=...
```

**`jj_deployments/.gitignore`**:

```text
**/secrets.env
```

### URI scheme

Source provenance is encoded in Turtle files as:

```text
jejuneness:doc/<repo-name>/<repo-relative-path>#L<start_line>-<end_line>
```

Example:

```text
jejuneness:doc/jj_doc_Collecting_Gold_Dust/result_data/CollectingGoldDust.md#L42-L55
```

The `<repo-name>` segment maps directly to a catalog entry. The `jj_workflow_shell` pipeline
writes these URIs; `jj_vis_net_viewer` and `jj_markdown_browser` parse and resolve them.

Resolution to a `jj_markdown_browser` container path:

```text
jejuneness:doc/<repo-name>/<path>#L<s>-<e>
    → /config/<repo-name>/<path>   (absolute container path)
    → #sel=/config/<repo-name>/<path>:<s>:1:<e>:999   (URL fragment)
```

### Working process

**Adding a new public `jj_doc_*` repository:**

1. Update `jj_workflow_shell/catalog-reference.yaml` with the new entry.
2. Each deployment adopts the new repo by adding the same entry to its own `catalog.yaml`
   — opt-in, not automatic.

**Creating a new deployment:**

```bash
# 1. Create the deployment directory
mkdir jj_deployments/deploy_AA

# 2. Bootstrap from scaffolds
cp jj_workflow_shell/catalog-reference.yaml jj_deployments/deploy_AA/catalog.yaml
cp jj_workflow_shell/env-reference          jj_deployments/deploy_AA/secrets.env

# 3. Customise
#    - Edit catalog.yaml: remove unwanted repos, add private repos if applicable
#    - Edit secrets.env: fill in credentials
#    - Create deployment.env with JJ_DOCS_ROOT and other non-secret config

# 4. Commit (secrets.env is gitignored automatically)
git -C jj_deployments add deploy_AA/catalog.yaml deploy_AA/deployment.env
git -C jj_deployments commit -m "Add deploy_AA deployment"
```

**Running the pipeline for a deployment:**

```bash
cd jj_deployments/deploy_AA
source ../../jj_workflow_shell/treatments.sh
source deployment.env
source secrets.env        # local only, not committed
jj_extract_knowledge_graph ...
```

**Running `jj_markdown_browser` for a deployment:**

A launcher script reads `catalog.yaml` and generates the `-v` mount flags automatically,
mounting each repo's `result_data/` at `/config/<repo-name>/` inside the container:

```bash
# jj_markdown_browser/run.sh <path-to-deployment-dir>
docker run -d \
  -v <workspace>/jj_doc_Collecting_Gold_Dust/result_data:/config/jj_doc_Collecting_Gold_Dust \
  -v <workspace>/jj_doc_Rob_Burbea/result_data:/config/jj_doc_Rob_Burbea \
  -p 8443:8443 jejuneness:code-server-uri-opener
```

Adding a new document to a deployment catalog is sufficient for it to appear mounted in the
next `run.sh` invocation — no other change is needed in `jj_markdown_browser`.
