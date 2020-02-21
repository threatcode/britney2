#!/bin/sh

set -e

# Create empty files and other required directories
mkdir -p data/state
touch data/state/age-policy-dates
touch data/state/age-policy-urgencies
touch data/state/rc-bugs-testing
touch data/state/rc-bugs-unstable
touch data/state/piuparts-summary-testing.json
touch data/state/piuparts-summary-unstable.json

mkdir -p data/output

# Fetch autopkgtest results, reading DEBCI_API_KEY from a .env in the
# same directory.
# That key needs to be manually pre-generated on the debci instance
# itself, using the following command (where "britney" is just an
# arbitrary internal username that debci will associate to that key):
#
#   debci api setkey britney
. $(dirname $(readlink -f $0))/.env
wget --header="Auth-Key: $DEBCI_API_KEY" https://autopkgtest.kali.org/api/v1/test\?since=$(date +%s --date="15 days ago")  -O data/state/debci.json
