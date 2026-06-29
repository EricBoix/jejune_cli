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
jj_neo4j_launch_db  --help
jj_extract_knowledge_graph  --help
jj_dump_knowledge_graph_in_turtle --help
jj_neo4j_dump_database --help
jj_neo4j_restore_database --help
jj_neo4j_stop_db --help
```

## Notes and warnings

### Concerning neo4j database

- **WARNING**: the username/password given to the neo4j database are only **initial** values (valid when starting the database for the first time). Once the neo4j db has been initialized those values are "burned" into the `database` files...
- There seems to be many caveats with the name of a neo4j dump, among which
  - the [neo4j-admin](https://neo4j.com/docs/operations-manual/current/neo4j-admin-neo4j-cli/) utility does not allow to provide the filename of the dump.
  - when restoring some dump, the provided database name must have a length between 1 and 63 characters.
  - a neo4j username/password are part of/burnt into the dump and cannot be overwritten. When dumping a neo4j DB one must keep the (dump, username, password) triplet.
