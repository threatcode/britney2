#!/usr/bin/python3

import itertools
import json
import os
import re
import requests
import sys

## constants
SUITE_RE = re.compile(r'.*/debci_(?P<suite>[^.]+)\.')
ARCH_RE = re.compile(r'.*/debci_submit_(?P<arch>[^.]+)\.json')

# example: debci-testing-i386:green {"triggers": ["green/2" "other/n"]}
DEBCI_RE = re.compile(r'^(?:[^-]+)-(?P<suite>.+)-(?P<arch>[^-]+):(?P<pkg>[^\s]+) .*triggers": \["(?P<triggers>.+)"\]')

PIN_SUITES = {'unstable': 'experimental',
              'testing': 'unstable',
              'stable': 'proposed-updates',
              'oldstable': 'oldstable-proposed-updates',
              'kali-rolling': 'kali-dev'}

TMP_FILE = 'debci.amqp'

# FIXME: make the next 2 environment variables or command-line
# options, to ease testing
DEBCI_URL = 'https://autopkgtest.kali.org'
DEBCI_PRIORITY = 10

DEBCI_API_KEY = os.getenv("DEBCI_API_KEY", "")

# in a single query to debci
MAX_REQUESTS = 5000


## functions
def grouper(iterable, n, fillvalue = None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


def britney2debci(debci_input):
    for chunk in grouper(debci_input, MAX_REQUESTS):
        debci_out = {}

        for line in chunk:
            if line == None:
                break

            m = DEBCI_RE.search(line).groupdict()

            suite, arch, pkg, triggers = m['suite'], m['arch'], m['pkg'], m['triggers']

            pinned_packages = [t.split('/')[0] for t in triggers.split()]
            pin = ",".join(['src:{}'.format(p) for p in pinned_packages])

            if triggers == 'migration-reference/0':
                request = {'package': pkg, 'trigger': triggers}
            else:
                request = {'package': pkg, 'trigger': triggers,
                           'pin-packages': [[pin, PIN_SUITES[suite]]]}

            if arch not in debci_out.keys():
                debci_out[arch] = []
            debci_out[arch].append(request)

        for arch in debci_out.keys():
            debci_jobs = json.dumps(debci_out[arch], separators=(',',':'))
            yield arch, debci_jobs


def submit_jobs(infile, key):
    directory = os.path.dirname(infile)
    suite = SUITE_RE.search(infile).groupdict()['suite']

    # read all requests
    tmp_file = os.path.join(directory, TMP_FILE)
    os.rename(infile, tmp_file)
    with open(tmp_file, 'r') as f:
        debci_input = f.readlines()

    headers = {'Auth-Key': key}

    try:
        for arch, debci_jobs in britney2debci(debci_input):
            url = '{}/api/v1/test/{}/{}'.format(DEBCI_URL, suite, arch)
            data = {'tests': debci_jobs,
                    'priority': DEBCI_PRIORITY}
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
    except Exception as e:
        print("An exception occured: {}".format(e), file=sys.stderr)
        os.rename(tmp_file, infile)
    finally:
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)


## main
if __name__ == '__main__':
    args = sys.argv[1:]
    if not len(args) >= 1:
        s = os.path.basename(sys.argv[0])
        msg = "Usage: {} debci_input_file [debci_input_file ...]".format(s)
        print(msg, file=sys.stderr)
        sys.exit(1)

    for infile in args:
        if os.path.isfile(infile):
            submit_jobs(infile, DEBCI_API_KEY)
