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

# Fetch autopkgtest results
wget http://autopkgtest.kali.org/data/status/kali-rolling/amd64/packages.json -O data/state/debci.json
