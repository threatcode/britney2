#!/bin/bash

# This takes care of implementing the following routine:
#   - fetch previous results
#   - run britney2 to process those results and find out what new
#     tests are needed
#   - schedule those new tests
#  
# It's pretty generic, and the only required paramater is a britney2
# conf file as its first argument.

set -euo pipefail

usage() {
  echo "Usage: $0 [-n] [-b <debci_backlog_days>] [-s <secret_header_file>] [-p <debci_priority>] [-r 'hint1 hint2 [...]'] <britney2_conf_file>"
  echo "  -d <debci_backlog_days>  : how many days worth of autopkgtest results to fetch (default: 7); if 0, skip fetching results altogether"
  echo "  -s <secret_headers_file> : this file must contain at least a 'Auth-Key: <debci_api_key>' line (default: ./.secret-headers )"
  echo "  -p <debci_priority>      : use this priority when enqueuing jobs line (default: 5)"
  echo "  -n                       : dry-run mode that does not schedule any tests line (default: false)"
  echo "  -z                       : schedule private debci runs (default: public)"
  echo "  -r                       : comma-separated list of release hints to download and use, see https://release.debian.org/britney/hints (default: empty)"
  echo "  -h                       : this help text"
  echo
  echo "Example: $0 -d 15 -r 'elbrus,adsb' britney2-debsec-stable.conf"
}

## constants
B2_DIR=$(dirname $(readlink -f $0))

## functions
get_b2_conf_value() {
  local key=$1
  local conf_file=$2
  perl -ne 'print $1 if m/^'$key'\s*=\s*(.*)/' $conf_file
}

get_file_url() { # file://foo/bar -> foo/bar
  perl -pe 's|.*://||'
}

## CLI options
DEBCI_BACKLOG_DAYS="7"
DEBCI_PRIORITY="5"
DEBCI_PRIVATE_RUNS=""
SECRET_HEADERS_FILE=$B2_DIR/.secret-headers
RELEASE_HINTS=""
DRY_RUN_MODE=""
while getopts "d:r:s:p:znh" opt ; do
  case "$opt" in
    d) DEBCI_BACKLOG_DAYS="$OPTARG" ;;
    r) RELEASE_HINTS="${OPTARG//,/ }" ;;
    s) SECRET_HEADERS_FILE="$OPTARG" ;;
    p) DEBCI_PRIORITY="$OPTARG" ;;
    n) DRY_RUN_MODE="--simulate" ;;
    z) DEBCI_PRIVATE_RUNS="--debci-private-runs" ;;
    h) usage ; exit 0 ;;
  esac
done
shift $(($OPTIND - 1))

if [ $# != 1 ] ; then
  usage
  exit 2
fi

## main
b2_conf=$1

# bail out right away if conf file is missing
[ -f $b2_conf ] || { echo "could not read $b2_conf" ; exit 2 ; }

# cd to project directory
cd $B2_DIR

# get relevant britney2 configuration
adt_swift_file=$(get_b2_conf_value ADT_SWIFT_URL $b2_conf | get_file_url)
adt_output_file=$(get_b2_conf_value ADT_AMQP $b2_conf | get_file_url)
adt_ci_url=$(get_b2_conf_value ADT_CI_URL $b2_conf)
source_suite=$(echo $(get_b2_conf_value UNSTABLE $b2_conf) | perl -pe 's|.*/dists/||')

# create the 2 directories needed by britney2 (when no_age &&
# no_pipuparts && no_rcbugs)
mkdir -p $(dirname $adt_swift_file) $(dirname $adt_output_file)

# initialize some policy-specific files that need to exist
state_dir=$(dirname $adt_swift_file)
touch ${state_dir}/age-policy-dates
touch ${state_dir}/age-policy-urgencies
touch ${state_dir}/rc-bugs-testing
touch ${state_dir}/rc-bugs-unstable
touch ${state_dir}/piuparts-summary-testing.json
touch ${state_dir}/piuparts-summary-unstable.json

# fetch hints
for hint in $RELEASE_HINTS ; do
  scripts/get-release-team-hint.sh $hint
done

# fetch autopkgtest results
if [ $DEBCI_BACKLOG_DAYS != 0 ] ; then
  start_time=$(date +%s --date="$DEBCI_BACKLOG_DAYS days ago")
  url=${adt_ci_url}/api/v1/test?since=$start_time
  curl --fail -o ${adt_swift_file} --header @$SECRET_HEADERS_FILE $url
fi

# run britney2
./britney.py -v --config $b2_conf --distribution kali 

# schedule the new tests
./scripts/debci-put.py $DRY_RUN_MODE $DEBCI_PRIVATE_RUNS --debci-priority $DEBCI_PRIORITY --secret-headers-file $SECRET_HEADERS_FILE $source_suite $adt_output_file
