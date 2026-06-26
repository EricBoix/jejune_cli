# A set of shell level utilities when working in jejuneness

## Usage

Let us assume you are working in the `cwd_dir` where you wish to use/invoke the `jj_workflow_shell` utilities

### Fetch the workflow utilities

```bash
git clone https://github.com/EricBoix/jj_workflow_shell.git   # This repository
source jj_workflow_shell/treatments.sh 
```

### Configure the shell utilities

Copy the `jj_workflow_shell/env-reference` file to a new `.env` file (located in the `cwd_dir` directory) and customize the environment variables values of `.env` in order to suit your needs

```bash
cp jj_workflow_shell/env-reference .env
```

Note that some variables are only required by some `jj_<command>`.
For example the `LLM_*` variables are only required when using [`jj_extract_knowledge_graph`](./treatments.sh).

### Use the commands

```bash
jj_launch_neo4j_db  --help
jj_extract_knowledge_graph  --help
jj_dump_knowledge_graph_in_turtle --help
jj_dump_database --help
jj_restore_database --help
jj_stop_neo4j_db --help
```
