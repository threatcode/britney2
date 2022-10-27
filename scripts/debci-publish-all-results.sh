#!/bin/bash

set -eu

B2_DIR=$(dirname $(dirname $(readlink -f $0)))

## constants
SCRIPTS_DIR=$(dirname $(readlink -f $0))
DSA_LIST_URL="https://salsa.debian.org/security-tracker-team/security-tracker/-/raw/master/data/DSA/list"
DEBCI_HEADERS_FILE=${B2_DIR}/.secret-headers
DSA_MAX_LINES_TO_READ=100
DEBCI_MAX_DAYS=60
DEBCI_CACHE_FILE=/tmp/debci-cache.json

## main

# cd to project directory
cd $B2_DIR

# remove debci cache file
rm -f $DEBCI_CACHE_FILE

# grab public DSA list, limit ourselves to the most recent ones, and
# publish those
curl -fs $DSA_LIST_URL | head -n $DSA_MAX_LINES_TO_READ | grep -P '\] - ' | while read dist foo package version ; do
  case $dist in
    *buster*|*bullseye*)
      scripts/debci-publish.py --days $DEBCI_MAX_DAYS --secret-headers-file $DEBCI_HEADERS_FILE --debci-cache-file $DEBCI_CACHE_FILE $package $version ;;
    *)
      : ;;
  esac
done
