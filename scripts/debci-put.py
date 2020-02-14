#!/usr/bin/python3

import glob
import json
import os
import re
import sys


SUITE_RE = re.compile(r'.*/debci_(?P<suite>[^.]+)\.')
ARCH_RE = re.compile(r'.*/debci_submit_(?P<arch>[^.]+)\.json')

def britney2debci(output_dir, debci_file):
    debci_input = os.path.join(output_dir, debci_file)
    debci_real = os.path.join(output_dir, 'debci_submit_%s.json')
    nr_of_lines = 5000

    pin_suite = dict(unstable='experimental', testing='unstable', stable='proposed-updates', oldstable='oldstable-proposed-updates')
    pin_suite.update({'kali-rolling': 'kali-dev'})

    with open(debci_input, 'r') as f:
        debci = f.readlines()

    debci_out = dict()
    line_nr = 0
    there_is_more = False
    for line in debci:
        line_nr += 1
        if line_nr <= nr_of_lines:
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
                                       'pin-packages': [[pin, pin_suite[suite]]]})
        else:
            there_is_more = True
            break

    for arch in debci_out:
        with open(debci_real % arch, 'w') as f:
            # Let's not waste space
            f.write(json.dumps(debci_out[arch], separators=(',',':')))

    with open(debci_input, 'w') as f:
        if there_is_more:
            f.writelines(debci[nr_of_lines:])
        else:
            f.writelines('')


def put(infile, key):
    d = os.path.dirname(infile)

    myfile = os.path.join(d, 'debci.amqp')

    suite = SUITE_RE.search(infile).groupdict()['suite']

    os.rename(infile, myfile)

    while os.stat(myfile).st_size > 0:
        britney2debci(d, myfile)

        files = glob.glob("{}/debci_submit_*.json".format(d))
        for json_file in files:
            arch = ARCH_RE.search(json_file).groupdict()['arch']

            # Starting in 7.55.0, the --header option can take an argument in
            # @filename style, which then adds a header for each line in the input
            # file.
            cmd = """curl --fail --silent
                 --header "Auth-Key: {}"
                 --cacert /etc/ssl/ca-global/ca-certificates.crt
                 --form tests=@{}
                 https://ci.debian.net/api/v1/test/{}/{}""".format(key, json_file, suite, arch)
            print(open(json_file).readlines())
            print(cmd)
            # Make sure we don't submit this multiple times by accident
            os.remove(json_file)


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
