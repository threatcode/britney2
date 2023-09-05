#!/usr/bin/python3

# TODO: parse DSA?

import argparse
import datetime
import json
import logging
import os.path
import requests
import sys

from lib.common import get_secret_headers, SECRET_HEADERS_FILE


# functions
def fetch_results(days_ago, secret_headers_file, debci_url, debci_cache_file):
    if debci_cache_file and os.path.isfile(debci_cache_file):
        logging.info('loading debci results from {}'.format(debci_cache_file))
        with open(debci_cache_file) as f:
            return json.load(f)['results']

    ts_now = datetime.datetime.now()
    ts_start = ts_now - datetime.timedelta(days=days_ago)
    since = ts_start.strftime('%s')
    url = '{}/api/v1/test?since={}'.format(debci_url, since)

    try:
        headers = get_secret_headers(secret_headers_file)
        logging.info('fetching {} days of results from {}'.format(days_ago, debci_url))
        response = requests.get(url, headers=headers,
                                verify=True)
        response.raise_for_status()
    except Exception as e:
        logging.exception('could not fetch results')
        sys.exit(1)

    data = response.json()

    if debci_cache_file:
        logging.info('saving debci results to {}'.format(debci_cache_file))
        with open(debci_cache_file, 'w') as f:
            json.dump(data, f)

    return data['results']


def get_run_ids_for_trigger(results, trigger):
    matches = [r for r in results if r['trigger'] == trigger]
    run_ids = [m['run_id'] for m in matches]
    return run_ids


def publish_runs(run_ids, secret_headers_file, debci_url, simulate=False):
    try:
        url = '{}/api/v1/test/publish'.format(debci_url)
        data = {'run_ids': ','.join([str(i) for i in run_ids])}
        headers = get_secret_headers(secret_headers_file)
        logging.info('run_ids to publish: {}'.format(data))
        if not simulate:
            logging.info('posting publish request to {}'.format(debci_url))
            response = requests.post(url, headers=headers, data=data,
                                     verify=True)
            text = response.text
            if text.strip():
                logging.info(response.text)

            response.raise_for_status()
    except Exception as e:
        logging.exception('could not publish results')
        sys.exit(1)


def run(source_package, version, secret_headers_file,
        debci_url, debci_cache_file, days, simulate):
    trigger = '{}/{}'.format(source_package, version)
    logging.info('working on trigger {}'.format(trigger))

    results = fetch_results(days, secret_headers_file, debci_url,
                            debci_cache_file)
    runs_ids = get_run_ids_for_trigger(results, trigger)

    publish_runs(runs_ids, secret_headers_file, debci_url, simulate)


# CL options
parser = argparse.ArgumentParser(description='''Publish private debci runs''')
parser.add_argument('--log-level',
                    dest='log_level',
                    choices=['debug', 'info', 'warning', 'error'],
                    default='info',
                    help='level at which to log')
parser.add_argument('--simulate',
                    dest='simulate',
                    action='store_true',
                    default=False,
                    help='do not actually publish anything')
parser.add_argument('--days',
                    dest='days',
                    action='store',
                    required=False,
                    type=int,
                    default=7,
                    metavar='DAYS')
parser.add_argument('--debci-url',
                    dest='debci_url',
                    action='store',
                    required=False,
                    default='https://ci.debian.net',
                    metavar='DEBCI_URL')
parser.add_argument('--debci-cache-file',
                    dest='debci_cache_file',
                    action='store',
                    required=False,
                    default=None,
                    metavar='DEBCI_CACHE_FILE',
                    help='local debci cache file to store results in: won''t query debci if it exists')
parser.add_argument('--secret-headers-file',
                    dest='secret_headers_file',
                    action='store',
                    required=False,
                    default=SECRET_HEADERS_FILE,
                    metavar='DEBCI_MAX_REQUESTS')
parser.add_argument('source_package')
parser.add_argument('version')

# main
if __name__ == '__main__':
    args = parser.parse_args()

    logging.basicConfig(format='[%(asctime)s] %(filename)-20s %(levelname)-7s: %(message)s',
                        level=args.log_level.upper())

    run(args.source_package, args.version,
        args.secret_headers_file,
        args.debci_url, args.debci_cache_file,
        args.days, args.simulate)
