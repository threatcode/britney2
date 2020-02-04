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
