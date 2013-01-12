# -*- coding: utf-8 -*-

# Refactored parts from britney.py, which is/was:
# Copyright (C) 2001-2008 Anthony Towns <ajt@debian.org>
#                         Andreas Barth <aba@debian.org>
#                         Fabio Tranchitella <kobold@debian.org>
# Copyright (C) 2010-2012 Adam D. Barratt <adsb@debian.org>
# Copyright (C) 2012 Niels Thykier <niels@thykier.net>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.


import apt_pkg
from functools import partial
from itertools import chain, ifilter, ifilterfalse, izip, repeat
import re


from consts import (BINARIES, PROVIDES, DEPENDS, CONFLICTS,
                    RDEPENDS, RCONFLICTS)

binnmu_re = re.compile(r'^(.*)\+b\d+$')

def same_source(sv1, sv2, binnmu_re=binnmu_re):
    """Check if two version numbers are built from the same source

    This method returns a boolean value which is true if the two
    version numbers specified as parameters are built from the same
    source. The main use of this code is to detect binary-NMU.

    binnmu_re is an optimization to avoid "load global".
    """
    if sv1 == sv2:
        return 1

    m = binnmu_re.match(sv1)
    if m: sv1 = m.group(1)
    m = binnmu_re.match(sv2)
    if m: sv2 = m.group(1)

    if sv1 == sv2:
        return 1

    return 0


def ifilter_except(container, iterable=None):
    """Filter out elements in container

    If given an iterable it returns a filtered iterator, otherwise it
    returns a function to generate filtered iterators.  The latter is
    useful if the same filter has to be (re-)used on multiple
    iterators that are not known on beforehand.
    """
    if iterable is not None:
        return ifilterfalse(container.__contains__, iterable)
    return partial(ifilterfalse, container.__contains__)


def ifilter_only(container, iterable=None):
    """Filter out elements in which are not in container

    If given an iterable it returns a filtered iterator, otherwise it
    returns a function to generate filtered iterators.  The latter is
    useful if the same filter has to be (re-)used on multiple
    iterators that are not known on beforehand.
    """
    if iterable is not None:
        return ifilter(container.__contains__, iterable)
    return partial(ifilter, container.__contains__)


def undo_changes(lundo, systems, sources, binaries,
                 BINARIES=BINARIES, PROVIDES=PROVIDES):
    """Undoes one or more changes to testing

    * lundo is a list of (undo, item)-tuples
    * systems is the britney-py.c system
    * sources is the table of all source packages for all suites
    * binaries is the table of all binary packages for all suites
      and architectures

    The "X=X" parameters are optimizations to avoid "load global"
    in loops.
    """

    # We do the undo process in "4 steps" and each step must be
    # fully completed for each undo-item before starting on the
    # next.
    #
    # see commit:ef71f0e33a7c3d8ef223ec9ad5e9843777e68133 and
    # #624716 for the issues we had when we did not do this.


    # STEP 1
    # undo all the changes for sources
    for (undo, item) in lundo:
        for k in undo['sources']:
            if k[0] == '-':
                del sources["testing"][k[1:]]
            else:
                sources["testing"][k] = undo['sources'][k]

    # STEP 2
    # undo all new binaries (consequence of the above)
    for (undo, item) in lundo:
        if not item.is_removal and item.package in sources[item.suite]:
            for p in sources[item.suite][item.package][BINARIES]:
                binary, arch = p.split("/")
                if item.architecture in ['source', arch]:
                    del binaries["testing"][arch][0][binary]
                    systems[arch].remove_binary(binary)


    # STEP 3
    # undo all other binary package changes (except virtual packages)
    for (undo, item) in lundo:
        for p in undo['binaries']:
            binary, arch = p.split("/")
            if binary[0] == "-":
                del binaries['testing'][arch][0][binary[1:]]
                systems[arch].remove_binary(binary[1:])
            else:
                binaries_t_a = binaries['testing'][arch][0]
                binaries_t_a[binary] = undo['binaries'][p]
                systems[arch].remove_binary(binary)
                systems[arch].add_binary(binary, binaries_t_a[binary][:PROVIDES] + \
                     [", ".join(binaries_t_a[binary][PROVIDES]) or None])

    # STEP 4
    # undo all changes to virtual packages
    for (undo, item) in lundo:
        for p in undo['nvirtual']:
            j, arch = p.split("/")
            del binaries['testing'][arch][1][j]
        for p in undo['virtual']:
            j, arch = p.split("/")
            if j[0] == '-':
                del binaries['testing'][arch][1][j[1:]]
            else:
                binaries['testing'][arch][1][j] = undo['virtual'][p]


def old_libraries_format(libs):
    """Format old libraries in a smart table"""
    libraries = {}
    for i in libs:
        pkg, arch = i.split("/")
        pkg = pkg[1:]
        if pkg in libraries:
            libraries[pkg].append(arch)
        else:
            libraries[pkg] = [arch]
    return "\n".join("  " + k + ": " + " ".join(libraries[k]) for k in libraries) + "\n"



def register_reverses(packages, provides, check_doubles=True, iterator=None,
                      parse_depends=apt_pkg.parse_depends,
                      DEPENDS=DEPENDS, CONFLICTS=CONFLICTS,
                      RDEPENDS=RDEPENDS, RCONFLICTS=RCONFLICTS):
    """Register reverse dependencies and conflicts for a given
    sequence of packages

    This method registers the reverse dependencies and conflicts for a
    given sequence of packages.  "packages" is a table of real
    packages and "provides" is a table of virtual packages.

    iterator is the sequence of packages for which the reverse
    relations should be updated.

    The "X=X" parameters are optimizations to avoid "load global" in
    the loops.
    """
    if iterator is None:
        iterator = packages.iterkeys()
    else:
        iterator = ifilter_only(packages, iterator)

    for pkg in iterator:
        # register the list of the dependencies for the depending packages
        dependencies = []
        pkg_data = packages[pkg]
        if pkg_data[DEPENDS]:
            dependencies.extend(parse_depends(pkg_data[DEPENDS], False))
        # go through the list
        for p in dependencies:
            for a in p:
                dep = a[0]
                # register real packages
                if dep in packages and (not check_doubles or pkg not in packages[dep][RDEPENDS]):
                    packages[dep][RDEPENDS].append(pkg)
                # also register packages which provide the package (if any)
                if dep in provides:
                    for i in provides[dep]:
                        if i not in packages: continue
                        if not check_doubles or pkg not in packages[i][RDEPENDS]:
                            packages[i][RDEPENDS].append(pkg)
        # register the list of the conflicts for the conflicting packages
        if pkg_data[CONFLICTS]:
            for p in parse_depends(pkg_data[CONFLICTS], False):
                for a in p:
                    con = a[0]
                    # register real packages
                    if con in packages and (not check_doubles or pkg not in packages[con][RCONFLICTS]):
                        packages[con][RCONFLICTS].append(pkg)
                    # also register packages which provide the package (if any)
                    if con in provides:
                        for i in provides[con]:
                            if i not in packages: continue
                            if not check_doubles or pkg not in packages[i][RCONFLICTS]:
                                packages[i][RCONFLICTS].append(pkg)


def compute_reverse_tree(packages_s, pkg, arch,
                     set=set, flatten=chain.from_iterable,
                     RDEPENDS=RDEPENDS):
    """Calculate the full dependency tree for the given package

    This method returns the full dependency tree for the package
    "pkg", inside the "arch" architecture for a given suite flattened
    as an iterable.  The first argument "packages_s" is the binary
    package table for that given suite (e.g. Britney().binaries["testing"]).

    The tree (or graph) is returned as an iterable of (package, arch)
    tuples and the iterable will contain ("pkg", "arch") if it is
    available on that architecture.

    If "pkg" is not available on that architecture in that suite,
    this returns an empty iterable.

    The method does not promise any ordering of the returned
    elements and the iterable is not reusable.

    The flatten=... and the "X=X" parameters are optimizations to
    avoid "load global" in the loops.
    """
    binaries = packages_s[arch][0]
    if pkg not in binaries:
        return frozenset()
    rev_deps = set(binaries[pkg][RDEPENDS])
    seen = set([pkg])

    binfilt = ifilter_only(binaries)
    revfilt = ifilter_except(seen)

    while rev_deps:
        # mark all of the current iteration of packages as affected
        seen |= rev_deps
        # generate the next iteration, which is the reverse-dependencies of
        # the current iteration
        rev_deps = set(revfilt(flatten( binaries[x][RDEPENDS] for x in binfilt(rev_deps) )))
    return izip(seen, repeat(arch))