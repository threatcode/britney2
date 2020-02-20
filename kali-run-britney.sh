#!/bin/sh

LOGFILE=kali-run-britney.log

if [ -e "$LOGFILE" ]; then
    savelog -q -c 7 -l $LOGFILE
fi

KALI_PREPARE="yes"
case "$*" in
    *--no-prepare*)
	KALI_PREPARE="no"
	;;
esac

if [ "$KALI_PREPARE" = "yes" ]; then
    ./kali-prepare-data.sh >$LOGFILE 2>&1
else
    : >$LOGFILE
fi

./britney.py -c kali.conf -v >>$LOGFILE 2>&1

# Push autopkgtest results to debci, reading DEBCI_API_KEY from a .env
# in the same directory (see comment in kali-prepare-data.sh for
# details about key generation)
. $(dirname $(readlink -f $0))/.env
export DEBCI_API_KEY

./scripts/debci-put.py ./data/output/debci_*.input >> $LOGFILE 2>&1
