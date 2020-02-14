#!/usr/bin/python3

import glob
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

# in a single query to debci
MAX_REQUESTS = 5000


## functions
def britney2debci(debci_input):
    with open(debci_input, 'r') as f:
        debci = f.readlines()

    debci_out = dict()
    line_nr = 0
    there_is_more = False
    for line in debci:
        line_nr += 1
        if line_nr <= MAX_REQUESTS:
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
        else:
            there_is_more = True
            break

    with open(debci_input, 'w') as f:
        if there_is_more:
            f.writelines(debci[MAX_REQUESTS:])
        else:
            f.writelines('')

    for arch in debci_out:
        yield arch, json.dumps(debci_out[arch], separators=(',',':'))


def put(infile, key):
    directory = os.path.dirname(infile)

    myfile = os.path.join(directory, 'debci.amqp')

    suite = SUITE_RE.search(infile).groupdict()['suite']

    os.rename(infile, myfile)

    while os.stat(myfile).st_size > 0:
        for arch, debci_jobs in britney2debci(myfile):
            # Starting in 7.55.0, the --header option can take an argument in
            # @filename style, which then adds a header for each line in the input
            # file.
            cmd = """curl --fail --silent
                 --header "Auth-Key: {}"
                 --cacert /etc/ssl/ca-global/ca-certificates.crt
                 --form tests='{}'
                 https://ci.debian.net/api/v1/test/{}/{}""".format(key, debci_jobs, suite, arch)
            print(debci_jobs)
            print(cmd)


KEY = 'FIXME'

if __name__ == '__main__':
    args = sys.argv[1:]
    if not len(args) >= 1:
        s = os.path.basename(sys.argv[0])
        msg = "Usage: {} debci_input_file [debci_input_file ...]".format(s)
        print(msg, file=sys.stderr)
        sys.exit(1)

    for infile in args:
        put(infile, KEY)
