#!/usr/bin/python3

import argparse
import itertools
import json
import logging
import os
import re
import requests
import sys

from lib.common import get_secret_headers, SECRET_HEADERS_FILE


# constants
ARCH_RE = re.compile(r'.*/debci_submit_(?P<arch>[^.]+)\.json')

# example: debci-testing-i386:green {"triggers": ["green/2" "other/n"]}
DEBCI_RE = re.compile(r'^(?:[^-]+)-(?P<suite>.+)-(?P<arch>[^-]+):(?P<pkg>[^\s]+) .*triggers": \["(?P<triggers>.+)"\]')

TMP_FILE = 'debci.tmp'


# functions
def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


def britney2debci(debci_input, source_suite, debci_max_requests,
                  debci_private_runs):
    for chunk in grouper(debci_input, debci_max_requests):
        debci_out = {}
        # suite will be initialized when processing the 1st chunk; it
        # is guaranteed to remain the same for all lines in a given
        # chunk as we work on per-distribution input files
        suite = None

        for line in chunk:
            if line is None:
                break

            m = DEBCI_RE.search(line).groupdict()

            suite, arch, pkg, triggers = m['suite'], m['arch'], m['pkg'], m['triggers']

            pinned_packages = [t.split('/')[0] for t in triggers.split()]
            pin = ",".join(['src:{}'.format(p) for p in pinned_packages])

            request = {'is_private': debci_private_runs,
                       'package': pkg,
                       'trigger': triggers}

            if triggers != 'migration-reference/0':
                request.update({'pin-packages': [[pin, source_suite]],
                                'extra-apt-sources': [source_suite]})

            if arch not in debci_out.keys():
                debci_out[arch] = []
            debci_out[arch].append(request)

        for arch in debci_out.keys():
            debci_jobs = json.dumps(debci_out[arch], separators=(',', ':'))
            logging.info('yielding {} jobs for {}/{}'.format(len(debci_out[arch]), suite, arch))
            yield suite, arch, debci_jobs


def submit_jobs(infile, source_suite, debci_url, secret_headers_file,
                debci_priority, debci_max_requests, simulate,
                debci_private_runs):
    directory = os.path.dirname(infile)

    # read all requests
    tmp_file = os.path.join(directory, TMP_FILE)
    os.rename(infile, tmp_file)
    with open(tmp_file, 'r') as f:
        debci_input = f.readlines()

    try:
        headers = get_secret_headers(secret_headers_file)
        for suite, arch, debci_jobs in britney2debci(
                debci_input, source_suite,
                debci_max_requests, debci_private_runs):
            url = '{}/api/v1/test/{}/{}'.format(debci_url, suite, arch)
            data = {'tests': debci_jobs, 'priority': debci_priority}
            logging.debug('job to post: {}'.format(data))
            if not simulate:
                logging.info('about to post')
                response = requests.post(url, headers=headers, data=data,
                                         verify=True)
                text = response.text
                if text.strip():
                    logging.info(response.text)
                response.raise_for_status()
    except Exception:
        logging.exception('could not post')
        os.rename(tmp_file, infile)
        sys.exit(1)
    finally:
        if os.path.isfile(tmp_file):
            if simulate:
                os.rename(tmp_file, infile)
            else:
                os.remove(tmp_file)


# CL options
parser = argparse.ArgumentParser(description='''Enqueue debci runs''')
parser.add_argument('--log-level',
                    dest='log_level',
                    choices=['debug', 'info', 'warning', 'error'],
                    default='info',
                    help='level at which to log')
parser.add_argument('--simulate',
                    dest='simulate',
                    action='store_true',
                    default=False,
                    help='do not actually schedule any runs')
parser.add_argument('--debci-private-runs',
                    dest='debci_private_runs',
                    action='store_true',
                    default=False,
                    help='schedule private runs')
parser.add_argument('--debci-url',
                    dest='debci_url',
                    action='store',
                    required=False,
                    default='https://ci.debian.net',
                    metavar='DEBCI_URL')
parser.add_argument('--debci-priority',
                    dest='debci_priority',
                    action='store',
                    required=False,
                    default=10,
                    type=int,
                    metavar='DEBCI_PRIORITY')
parser.add_argument('--debci-max-requests',
                    dest='debci_max_requests',
                    action='store',
                    required=False,
                    default=500,
                    type=int,
                    metavar='DEBCI_MAX_REQUESTS')
parser.add_argument('--secret-headers-file',
                    dest='secret_headers_file',
                    action='store',
                    required=False,
                    default=SECRET_HEADERS_FILE,
                    metavar='DEBCI_MAX_REQUESTS')
parser.add_argument('source_suite')
parser.add_argument('debci_input_file',
                    nargs='+')


# main
if __name__ == '__main__':
    args = parser.parse_args()

    logging.basicConfig(format='[%(asctime)s] %(filename)-20s %(levelname)-7s: %(message)s',
                        level=args.log_level.upper())

    for infile in args.debci_input_file:
        if not os.path.isfile(infile):
            logging.critical("file {} does not exist".format(infile))
            sys.exit(2)

        logging.info('about to work on {}'.format(infile))
        submit_jobs(infile, args.source_suite, args.debci_url,
                    args.secret_headers_file, args.debci_priority,
                    args.debci_max_requests, args.simulate,
                    args.debci_private_runs)
