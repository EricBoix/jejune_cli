# !/bin/sh

jj_extract_knowledge_graph () {
  # Check that parameters are correctly provided
  if [ $# != 2 ]
    then
      echo "Two parameters must be provided to this function:"
      echo "  1. directory where the input documents are located"
      echo "  2. a string holding all the documents to load (with the flags)"
      return
  fi
  INPUT_DIR=$1
  INPUT_FILE_WITH_FLAGS=$2
  if [[ ! "$INPUT_DIR" = /* ]]; 
    then
    echo "The directory argument must be an absolute path."
    echo "The one provided was $1. Exiting."
    return
  fi

  docker build -t jejuneness:jj_build_knowledge_graph https://github.com/EricBoix/jj_build_knowledge_graph.git#:DockerContext
  docker run --rm --tty --name jj_build_knowledge_graph \
    --network host \
    -v $1:/data \
    --env-file .env \
    jejuneness:jj_build_knowledge_graph extracting_graph_semantic_chuncker.py --input_directory /data \
    $2
}

jj_dump_knowledge_graph_in_turtle () {
  if [ $# != 2 ]
    then
      echo "Two parameters must be provided to this script:"
      echo "  1. directory where the turtle file will be created."
      echo "  2. the target turtle filename (within the previous directory)"
      return
  fi
  DATABASE_DIR=$1
  if [[ ! "$DATABASE_DIR" = /* ]]; 
    then
    echo "The directory argument must be an absolute path."
    echo "The one provided was $1. Exiting."
    return
  fi
  FILENAME=$2
  docker build -t jejuneness:jj_neo4j_to_rdf_ttl https://github.com/EricBoix/jj_neo4j_to_rdf_ttl.git#:DockerContext
  docker run --rm \
    --network host \
    -v $DATABASE_DIR:/output \
    --env-file .env \
    jejuneness:jj_neo4j_to_rdf_ttl \
    neo4j_to_rdf.py /output/$FILENAME
}

jj_server_test_inference() {
  if ! command -v curl >/dev/null 2>&1
    then
        echo "curl command could not be found. Exiting."
        exit 1
  fi
  echo -n "Testing LLM server $LLM_MODEL_URL access with api_key $LLM_API_KEY:"
  if curl -fsS -X GET "$LLM_MODEL_URL/api/tags" -H 'Authorization: BEARER '$LLM_API_KEY >/dev/null 2>&1
  # On some OpenwebUI servers (this is configuration dependent) the endpoint
  #   /api/v1/chats/
  #   /api/v1/users/
  #   /api/v1/users/me
  #   /api/v1/auths/signin
  # have no authentication enforced at all (every endpoint returns 200 without
  # any key).
  then
    echo " ok."
  else
    echo "failed. Exiting."
    return 1
  fi
  echo -n "Testing LLM inference request on $LLM_MODEL_URL:"
  if curl -fsS -X 'POST' "$LLM_MODEL_URL/api/generate" -H 'Authorization: BEARER '$LLM_API_KEY -H 'Content-Type: application/json' -d '{ "model": "'$LLM_MODEL_NAME'", "prompt": "How are you today?"}' >/dev/null 2>&1
  then
    echo " ok."
  else
    echo "failed. Exiting."
    return 1
  fi
}