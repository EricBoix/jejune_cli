set -a
if [ ! -f .env ]; then
    echo "Environment file .env not found! Exiting."
    return 1
fi
source .env
DIR_OF_THIS_SCRIPT="$(dirname "$(realpath "$BASH_SOURCE")")"
if [ ! -d $DIR_OF_THIS_SCRIPT ]; then
    echo "Directory $DIR_OF_THIS_SCRIPT of scripts not found. Exiting."
    return 1
fi
source $DIR_OF_THIS_SCRIPT/Neo4jDatabase.sh 
source $DIR_OF_THIS_SCRIPT/treatments.sh
set +a