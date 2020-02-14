#!/usr/bin/python3

import itertools
import json
import os
import re
import sys

## constants
SUITE_RE = re.compile(r'.*/debci_(?P<suite>[^.]+)\.')
ARCH_RE = re.compile(r'.*/debci_submit_(?P<arch>[^.]+)\.json')

PIN_SUITES = {'unstable': 'experimental',
              'testing': 'unstable',
              'stable': 'proposed-updates',
              'oldstable': 'oldstable-proposed-updates',
              'kali-rolling': 'kali-dev'}

TMP_FILE = 'debci.amqp'

DEBCI_URL = 'http://autopkgtest.kali.org'

DEBCI_API_KEY = os.getenv("DEBCI_API_KEY", "")

# in a single query to debci
MAX_REQUESTS = 5000


## functions
def grouper(iterable, n, fillvalue = None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


def britney2debci(debci_input_file):
    with open(debci_input_file, 'r') as f:
        debci = f.readlines()

    for chunk in grouper(debci, MAX_REQUESTS):
        debci_out = {}

        for line in chunk:
            if line == None:
                break

            # example:
            # debci-testing-i386:green {"triggers": ["green/2"]}
            (queue, package) = line.split()[0].split(':')
            (_, suite, arch) = re.match(r'([^-]+)-(.+)-([^-]+)', queue).groups()
            triggers = line.split(' ["')[1].split('"]}')[0]
            pin = ",".join('src:%s' % t.split('/')[0] for t in triggers.split())
            if arch not in debci_out:
                debci_out[arch] = list()
            if triggers == 'migration-reference/0':
                debci_out[arch].append({'package': package, 'trigger': triggers})
            else:
                debci_out[arch].append({'package': package, 'trigger': triggers,
                                       'pin-packages': [[pin, PIN_SUITES[suite]]]})

        for arch in debci_out.keys():
            debci_jobs = json.dumps(debci_out[arch], separators=(',',':'))
            yield arch, debci_jobs


def put(infile, key):
    directory = os.path.dirname(infile)
    suite = SUITE_RE.search(infile).groupdict()['suite']

    tmp_file = os.path.join(directory, TMP_FILE)
    os.rename(infile, tmp_file)

    for arch, debci_jobs in britney2debci(tmp_file):
        # Starting in 7.55.0, the --header option can take an argument in
        # @filename style, which then adds a header for each line in the input
        # file.
        cmd = """curl --fail --silent
             --header "Auth-Key: {}"
             --cacert /etc/ssl/ca-global/ca-certificates.crt
             --form tests='{}'
             {}/api/v1/test/{}/{}""".format(key, debci_jobs, KALI_DEBCI_URL, suite, arch)
        print(cmd)

if __name__ == '__main__':
    args = sys.argv[1:]
    if not len(args) >= 1:
        s = os.path.basename(sys.argv[0])
        msg = "Usage: {} debci_input_file [debci_input_file ...]".format(s)
        print(msg, file=sys.stderr)
        sys.exit(1)

    for infile in args:
        put(infile, DEBCI_API_KEY)
