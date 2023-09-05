#!/bin/bash

set -eu

## constants
HINTS_BASE_URL=https://release.debian.org/britney/hints
HINTS_DIR=hints

## main

if [ $# != 1 ] ; then
  echo "Usage: $0 <release_team_member"
  exit 2
fi

name=$1

mkdir -p $HINTS_DIR
curl -fs ${HINTS_BASE_URL}/$name >| ${HINTS_DIR}/$name
