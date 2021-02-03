#!/usr/bin/python3

import apt_pkg
import copy
import os.path
import urllib.request


import britney
import britney2
import britney2.hints


DEBIAN_RELEASE_MANAGERS = ('adsb',
                           'elbrus',
                           'ginggs',
                           'ivodd',
                           'jcristau',
                           'jmw',
                           'kibi',
                           'pochu',
                           'sramacher')

DEBIAN_HINTS_URL = 'https://release.debian.org/britney/hints/'


# FIXME: monkey-patching...
class HashableHint(britney2.hints.Hint):
    def __repr__(self):
        return f'{self.user} {self._type} {self.package}: s={self.suite.name}, v={self.version}, a={self.architecture}'

    def __hash__(self):
        return hash((self._user, self._active, self._type, tuple(sorted(self.packages))))
britney2.hints.Hint = HashableHint


class HashableMigrationItem(britney2.migrationitem.MigrationItem):
    def __hash__(self):
        return hash((self.uvname, self.version))
britney2.migrationitem.MigrationItem = HashableMigrationItem


def download_debian_hints(debian_release_manager):
    url = os.path.join(DEBIAN_HINTS_URL, debian_release_manager)
    content = urllib.request.urlopen(url).read()
    # FIXME: keep a local copy
    # with open(f'{debian_release_manager}.txt', 'wb') as f:
    #     f.write(content)
    return content.decode('utf-8')


def register_debian_hints(brit):
    for debian_release_manager in DEBIAN_RELEASE_MANAGERS:
        brit.logger.info(f'Loading hints list for debian/{debian_release_manager}')
        hints = download_debian_hints(debian_release_manager)
        hints_lines = hints.split('\n')
        brit._hint_parser.parse_hints(debian_release_manager,
                                      britney.Britney.HINTS_ALL,
                                      debian_release_manager,
                                      hints_lines)


def get_frozen_hints(brit):
    return copy.deepcopy(brit.hints)


def affects(brit, target_suite, hint):
    # FIXME: discard architectures not present in kali right away
    # FIXME: handle architecture/bin vs src differently
    # FIXME: implement proper check for block
    # FIXME: implement proper check for force-badtest

    pkg = hint.package
    version = hint.version

    if pkg not in hint.suite.sources:
        # that pkg in not in kali-dev at all
        return False, None

    if pkg not in target_suite.sources:
        # that pkg in not in kali-rolling at all
        return True, f'- to {version}'

    testing_version = target_suite.sources[pkg].version

    if version == 'all':
        # FIXME: check if testing_version < unstable_version?
        verdict = True
    elif version is None:
        # FIXME?
        verdict = False
    else:
        unstable_version = hint.suite.sources[pkg].version

        if apt_pkg.version_compare(unstable_version, version) < 0:
            # version in kali-dev is lower than hinted one
            verdict = False
        else:
            # version in kali-rolling lower than hinted one?
            cmp = apt_pkg.version_compare(testing_version, version)
            verdict = cmp < 0

    return verdict, f'{testing_version} to {version}'


if __name__ == '__main__':
    # initialize britney and store its hints
    brit = britney.Britney()
    kali_hints = get_frozen_hints(brit)

    # reset hints
    brit._hint_parser = britney2.hints.HintParser(brit._migration_item_factory)
    brit._policy_engine.register_policy_hints(brit._hint_parser)

    # import and read debian hints
    register_debian_hints(brit)
    debian_hints = get_frozen_hints(brit)

    print(kali_hints, len(kali_hints._hints))
    print(debian_hints, len(debian_hints._hints))

    diff = set(debian_hints._hints) - set(kali_hints._hints)
    target_suite = brit.suite_info.target_suite
    for hint in diff:
        verdict, migration = affects(brit, target_suite, hint)
        if verdict:
            print(hint, migration)
