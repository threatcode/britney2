import re


SECRET_HEADERS_FILE = '.secret-headers'


def get_secret_headers(secret_headers_file=SECRET_HEADERS_FILE):
    secret_headers = {}
    with open(secret_headers_file) as f:
        for line in f.readlines():
            k, v = re.split(r':\s+', line.strip())
            secret_headers[k] = v
    return secret_headers
