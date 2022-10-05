#!/bin/sh

set -eu

URL=https://release.debian.org/britney/hints/elbrus
OUTFILE=Hints/bad-tests

if [ ! -e $OUTFILE ]; then
    echo "ERROR: $OUTFILE doesn't exist" >&2
    exit 1
fi

cat << EOF > $OUTFILE
# Synchronized with $URL on $(date --iso-8601)
# using the script $(basename $0).
EOF

wget $URL -O- \
| sed '/^ *finished/,$d' \
| grep '^ *force-badtest ' \
| LC_ALL=C sort \
>> $OUTFILE
