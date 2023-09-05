This document describes how the autopkgtests-based regression testing is
automated for security updates.

# Tooling #

## Code ##

It can be found in [the team's britney2
repository](https://salsa.debian.org/security-team/britney2,).

### Running tests, handling results ###

The main entrypoint, run periodically via cron, is
[run-standalone.sh](https://salsa.debian.org/security-team/britney2/-/blob/master/run-standalone.sh)
(with some scripts used by `run-standalone.sh` under `scripts/`). Its
usage is as follows:

```
Usage: ./run-standalone.sh [-n] [-d <debci_backlog_days>] [-s <secret_headers_file>] [-r 'hint1 hint2 [...]'] <britney2_conf_file>
  -d <debci_backlog_days>  : how many days worth of autopkgtest results to fetch (default: 7)
  -s <secret_headers_file> : this file must contain an 'Auth-Key: <debci_api_key>' line (default: ./.secret-headers )
  -p <debci_priority>      : use this priority when enqueuing jobs line (default: 5)
  -n                       : dry-run mode that does not schedule any tests line (default: false)
  -z                       : schedule private debci runs (default: public)
  -r                       : comma-separated list of release hints to download and use, see https://release.debian.org/britney/hints (default: empty)
  -h                       : this help text

Example: ./run-standalone.sh -d 15 -r 'elbrus,adsb' britney2-debsec-stable.conf
```

This takes care of implementing the following routine:

  - fetch previous results
  - run britney2 to process those results and find out what new tests are needed
  - schedule those new tests
  
It's pretty generic, and the only required paramater is a britney2 conf
file as its first argument.

### Publishing results for public DSAs ###

[scripts/debci-publish-all-results.sh](https://salsa.debian.org/security-team/britney2/-/blob/master/scripts/debci-publish-all-results.sh) runs periodically via cron, and leverages [scripts/debci-publish.py]( https://salsa.debian.org/security-team/britney2/-/blob/master/scripts/debci-publish.py). It ensures the tests results for public DSAs are made publically accessible on <https://ci.debian.net/user/security-team/jobs>.

## Configuration ##

The configuration file for the stable release is
[etc/autopkgtest_stable-security.conf](https://salsa.debian.org/security-team/britney2/-/blob/master/etc/autopkgtest_stable-security.conf). It
describes where the control files can be found (on `seger.debian.org`),
what architectures are supported, etc.

There is another configuration file for the oldstable release, used when
the *DebSec Team* supports it:
[etc/autopkgtest_oldstable-security.conf](https://salsa.debian.org/security-team/britney2/-/blob/master/etc/autopkgtest_oldstable-security.conf).

# Deployment #

## Layout ##

Everything is deployed on `seger.debian.org`:

  * the base dir is `/srv/security-team.debian.org/autopkgtest/`.

  * the britney2 code mentioned above is checked out in
    `/srv/security-team.debian.org/autopkgtest/britney2`.

  * `/srv/security-team.debian.org/autopkgtest/britney2/.secret-headers`
    is manually populated with the *DebSec Team* security token for
    `ci.debian.net`.

  * the `respighi` data describing the state of the stable release is
    under
    `/srv/security-team.debian.org/autopkgtest/respighi-mirror/stable`,
    and for the oldstable release under
    `/srv/security-team.debian.org/autopkgtest/respighi-mirror/oldstable`.

## Manual syncing of point release data ##

Right now `respighi.debian.org:/srv/mirrors/debian/dists/{,old}stable`
have be manually rsync'ed, until DSA solves
<https://rt.debian.org/Ticket/Display.html?id=8802>. It means that for
every point release the data from `resphigi.debian.org` needs to be
manually synced. This operation can be performed using the following
rsync-based sequence:

```
for dist in stable oldstable ; do
  d=$debsec/autopkgtest/mirrors/$dist/
  rsync -L -aHvPz --exclude images/ respighi.debian.org:/srv/mirrors/debian/dists/$dist/ $d
  rsync -L -aHvPz --exclude images/ $d seger.debian.org:/srv/security-team.debian.org/autopkgtest/respighi-mirror/$dist/
done
```

## Cron automation ##

`run.sh` is run with 7 days of backlog, and only `elbrus` hints. Here is
the corresponding cron entries for stable on `seger.debian.org`:

```
# Regression testing (via debci) for stable
# The resulting excuses file can be viewed with:
#    elinks /srv/security-team.debian.org/autopkgtest/britney2/data-stable/output/excuses_buildd-stable-security.html 
30 * * * * /srv/security-team.debian.org/autopkgtest/britney2/run-standalone.sh -p 9 -z -r elbrus /srv/security-team.debian.org/autopkgtest/britney2/etc/autopkgtest_stable-security.conf >> /srv/security-team.debian.org/autopkgtest/britney2/logs/autopkgtest_stable-security.log 2>&1
```

For oldstable it's:

```
# Regression testing (via debci) for oldstable
# The resulting excuses file can be viewed with:
#    elinks /srv/security-team.debian.org/autopkgtest/britney2/data-oldstable/output/excuses_buildd-oldstable-security.html
40 * * * * /srv/security-team.debian.org/autopkgtest/britney2/run-standalone.sh -p 9 -z -r elbrus /srv/security-team.debian.org/autopkgtest/britney2/etc/autopkgtest_oldstable-security.conf >> /srv/security-team.debian.org/autopkgtest/britney2/logs/autopkgtest_oldstable-security.log 2>&1
```

Results are published with:

```
# Publish results for regression testing runs that correspond to DSAs
# that are already publically released
# The corresponding logs are in /srv/security-team.debian.org/autopkgtest/britney2/logs/debci-publish-all-results.log*
5 * * * * /srv/security-team.debian.org/autopkgtest/britney2/scripts/debci-publish-all-results.sh >> /srv/security-team.debian.org/autopkgtest/britney2/logs/publish.log 2>&1

```

## Logs ##

`run-standalone.sh` logs for stable-security: `/srv/security-team.debian.org/autopkgtest/britney2/logs/autopkgtest_stable-security.log` 

`run-standalone.sh` logs for oldstable-security: `/srv/security-team.debian.org/autopkgtest/britney2/logs/autopkgtest_oldstable-security.log`

Publishing logs: `/srv/security-team.debian.org/autopkgtest/britney2/logs/publish.log`

# Checking results #

You need to login on `seger.debian.org`, and look at the HTML results
produced by britney2.

For stable:

`elinks /srv/security-team.debian.org/autopkgtest/britney2/data-stable/output/excuses_buildd-stable-security.html`

For oldstable:

`elinks /srv/security-team.debian.org/autopkgtest/britney2/data-stable/output/excuses_buildd-oldstable-security.html`
