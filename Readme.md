# A set of shell level utilities

## Usage

### Fetch the workflow utilities

```bash
git clone https://github.com/EricBoix/jj_worflow_shell.git
source jj_worflow_shell/Neo4jDatabase.sh 
source jj_worflow_shell/treatments.sh 
```

### Configure the scripts (setting environnement variables)

Most of the [treatment methods](./treatments.sh) require a running neo4j database. In order to configure that database define the following parameter values in order to suit your needs

```bash
export NEO4J_PORT=7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=your_password
```

and then transmit that configuration (through a shell environment file) to upcoming treatment processes:

```bash
echo "# Neo4j server designation and associated credentials" > .env
echo "NEO4J_URI=bolt://localhost:$NEO4J_PORT"                >> .env
echo "NEO4J_USERNAME=$NEO4J_USERNAME"                        >> .env
echo "NEO4J_PASSWORD=$NEO4J_PASSWORD"                        >> .env
```

Some [treatment methods](./treatments.sh) also require the setup of an LLM server. When needed, adapt the following designation and credentials

```bash
LLM_MODEL_URL=https://ollama-ui.pagoda.liris.cnrs.fr/ollama/
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL_NAME=llama3:70b
```

and also transmit that configuration (through a shell environment file)

```bash
echo "### LLM server designation and associate credential" >> .env
echo "MODEL_URL=$LLM_MODEL_URL"                            >> .env
echo "API_KEY=$LLM_API_KEY"                                >> .env
echo "MODEL=$LLM_MODEL_NAME"                               >> .env
```
