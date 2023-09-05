#!/bin/sh

set -e

# The debci api key needs to be manually pre-generated on the debci instance
# itself, using the following command (where "britney" is just an arbitrary
# internal username that debci will associate to that key):
#
#   debci api setkey britney
#
# The key is then placed in the file .secret-headers, so that it's used
# automatically by run-standalone.sh and other scripts.

# About the arguments "-d <debci_backlog_days>" and "-p <debci_priority>": we
# don't use the default values for those, we stick to Kali "historical config"
# to make sure not to break anything, but really I don't know if that's
# required.

LOGFILE=kali-run-britney.log

if [ -e "$LOGFILE" ]; then
    savelog -q -c 7 -l $LOGFILE
fi

./run-standalone.sh -d 15 -p 10 kali.conf >$LOGFILE 2>&1
