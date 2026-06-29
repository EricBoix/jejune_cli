# !/bin/sh

jj_neo4j_launch_db () {
  # Check that parameters are correctly provided
  if [ $# != 3 ]
    then
      echo "Three parameters must be provided to this function:"
      echo "  1. directory of execution: where the database subfolder will"
      echo "     be created by the neo4j database"
      echo "  2. the port on which the DB server can be contacted"
      echo "  3. a single string holding <user_name>/<password>"
      return
  fi
  DIR=$1
  if [[ ! "$DIR" = /* ]]; 
    then
    echo "The directory argument must be an absolute path."
    echo "The one provided was $1. Exiting."
    return
  fi
  PORT=$2
  USER_PASSWORD=$3
  IMAGE_NAME='jejuness:jj_neo4j_docker'
  CONTAINER_NAME=jj_neo4j_db

  echo "Building image."
  docker build -t $IMAGE_NAME https://github.com/EricBoix/jj_neo4j_docker.git

  docker run --rm --detach --name $CONTAINER_NAME \
      --publish=7474:7474 --publish=$PORT:7687 \
      --env NEO4J_AUTH=$USER_PASSWORD \
      -v $DIR/database:/data \
      $IMAGE_NAME
  
  # Alas neo4j container has no health check. Wait for it to be running and
  # then just wait some more...
  until [ "`docker inspect -f {{.State.Running}} $CONTAINER_NAME`"=="true" ]; do
    echo "."
    sleep 0.5;
  done;
  echo "Waiting for some arbitrary, and hopefully sufficient, time for neo4j"
  sleep 5
   
  echo "Done with launching of Neo4j DB on port $PORT"
}

jj_neo4j_stop_db () {
  CONTAINER_NAME=jj_neo4j_db
  echo "Halting the Neo4j database server."
  echo "  Stopping container $CONTAINER_NAME"
  docker stop $CONTAINER_NAME 2> /dev/null
  echo "  Removing container $CONTAINER_NAME"
  docker rm $CONTAINER_NAME 2> /dev/null
  echo "Neo4j database server now halted."
}

jj_neo4j_dump_database () {
  # Check that parameters are correctly provided
  if [ $# != 2 ]
    then
      echo "Two parameters must be provided to this function:"
      echo "  1. directory where the database (as files) subfolder and backup"
      echo "     subfolder (holding dump files) are located"
      echo "  2. the database-dump target filename (same directory as dumped)"
      return
  fi
  RESULTS_DIR=$1
  if [[ ! "$RESULTS_DIR" = /* ]]; 
    then
    echo "The directory argument must be an absolute path."
    echo "The one provided was $1. Exiting."
    return
  fi
  DATABASE_DIR=$RESULTS_DIR/database
  BACKUPS_DIR=$RESULTS_DIR/backups
  DUMP_FILENAME=$2

  # Dumping requires the DB to be halted properly
  jj_neo4j_stop_db
  docker run --interactive --tty --rm  \
    --volume=$DATABASE_DIR:/data \
    --volume=$BACKUPS_DIR:/output \
    neo4j/neo4j-admin neo4j-admin database dump neo4j --to-path=/output
  # neo4j-admin does not allow to provide the filename of the dump.
  # Note: alas, when restoring the dump, the provided database name must have a 
  # length between 1 and 63 characters...
  mv $BACKUPS_DIR/neo4j.dump $BACKUPS_DIR/$2
}

jj_neo4j_restore_database () {
  # Check that parameters are correctly provided
  if [ $# != 2 ]
    then
      echo "Two parameters must be provided to this function:"
      echo "  1. directory where the database (as files) subfolder and backup"
      echo "     subfolder (holding dump files) are located"
      echo "  2. the database-dump target filename (same directory as dumped)"
      return
  fi
  RESULTS_DIR=$1
  if [[ ! "$RESULTS_DIR" = /* ]]; 
    then
    echo "The directory argument must be an absolute path."
    echo "The one provided was $1. Exiting."
    return
  fi
  DATABASE_DIR=$RESULTS_DIR/database
  BACKUPS_DIR=$RESULTS_DIR/backups
  DUMP_FILENAME=$2
  
  # In order to avoid possible conflict with already running db, DB restoration
  # requires its halting 
  jj_neo4j_stop_db
  # Clean up the current database content
  \rm -fr $DATABASE_DIR
  # The name of the dumped database file DID NOT matter: we still have to 
  # restore it properly (without any choice for the target filename)
  \cp $BACKUPS_DIR/$2 $BACKUPS_DIR/neo4j.dump
  docker run --interactive --tty --rm \
    --volume=$DATABASE_DIR:/data \
    --volume=$BACKUPS_DIR:/backups \
    neo4j/neo4j-admin neo4j-admin database load neo4j --from-path=/backups
  return 0
}