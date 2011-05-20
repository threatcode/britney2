#!/usr/bin/python2.5
# -*- coding: utf-8 -*-

# Copyright (C) 2001-2008 Anthony Towns <ajt@debian.org>
#                         Andreas Barth <aba@debian.org>
#                         Fabio Tranchitella <kobold@debian.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

"""
= Introdution =

This is the Debian testing updater script, also known as "Britney".

Packages are usually installed into the `testing' distribution after
they have undergone some degree of testing in unstable. The goal of
this software is to do this task in a smart way, allowing testing
to be always fully installable and close to being a release candidate.

Britney's source code is split between two different but related tasks:
the first one is the generation of the update excuses, while the
second tries to update testing with the valid candidates; first 
each package alone, then larger and even larger sets of packages
together. Each try is accepted if testing is not more uninstallable
after the update than before.

= Data Loading =

In order to analyze the entire Debian distribution, Britney needs to
load in memory the whole archive: this means more than 10.000 packages
for twelve architectures, as well as the dependency interconnections
between them. For this reason, the memory requirements for running this
software are quite high and at least 1 gigabyte of RAM should be available.

Britney loads the source packages from the `Sources' file and the binary
packages from the `Packages_${arch}' files, where ${arch} is substituted
with the supported architectures. While loading the data, the software
analyzes the dependencies and builds a directed weighted graph in memory
with all the interconnections between the packages (see Britney.read_sources
and Britney.read_binaries).

Other than source and binary packages, Britney loads the following data:

  * BugsV, which contains the list of release-critical bugs for a given
    version of a source or binary package (see Britney.read_bugs).

  * Dates, which contains the date of the upload of a given version 
    of a source package (see Britney.read_dates).

  * Urgencies, which contains the urgency of the upload of a given
    version of a source package (see Britney.read_urgencies).

  * Hints, which contains lists of commands which modify the standard behaviour
    of Britney (see Britney.read_hints).

For a more detailed explanation about the format of these files, please read
the documentation of the related methods. The exact meaning of them will be
instead explained in the chapter "Excuses Generation".

= Excuses =

An excuse is a detailed explanation of why a package can or cannot
be updated in the testing distribution from a newer package in 
another distribution (like for example unstable). The main purpose
of the excuses is to be written in an HTML file which will be 
published over HTTP. The maintainers will be able to parse it manually
or automatically to find the explanation of why their packages have
been updated or not.

== Excuses generation ==

These are the steps (with references to method names) that Britney
does for the generation of the update excuses.

 * If a source package is available in testing but it is not
   present in unstable and no binary packages in unstable are
   built from it, then it is marked for removal.

 * Every source package in unstable and testing-proposed-updates,
   if already present in testing, is checked for binary-NMUs, new
   or dropped binary packages in all the supported architectures
   (see Britney.should_upgrade_srcarch). The steps to detect if an
   upgrade is needed are:

    1. If there is a `remove' hint for the source package, the package
       is ignored: it will be removed and not updated.

    2. For every binary package built from the new source, it checks
       for unsatisfied dependencies, new binary package and updated
       binary package (binNMU) excluding the architecture-independent
       ones and the packages not built from the same source.

    3. For every binary package built from the old source, it checks
       if it is still built from the new source; if this is not true
       and the package is not architecture-independent, the script
       removes it from testing.

    4. Finally, if there is something worth doing (eg. a new or updated
       binary package) and nothing wrong it marks the source package
       as "Valid candidate", or "Not considered" if there is something
       wrong which prevented the update.

 * Every source package in unstable and testing-proposed-updates is
   checked for upgrade (see Britney.should_upgrade_src). The steps
   to detect if an upgrade is needed are:

    1. If the source package in testing is more recent the new one
       is ignored.

    2. If the source package doesn't exist (is fake), which means that
       a binary package refers to it but it is not present in the
       `Sources' file, the new one is ignored.

    3. If the package doesn't exist in testing, the urgency of the
       upload is ignored and set to the default (actually `low').

    4. If there is a `remove' hint for the source package, the package
       is ignored: it will be removed and not updated.

    5. If there is a `block' hint for the source package without an
       `unblock` hint or a `block-all source`, the package is ignored.

    6. If there is a `block-udeb' hint for the source package, it will
       have the same effect as `block', but may only be cancelled by
       a subsequent `unblock-udeb' hint.

    7. If the suite is unstable, the update can go ahead only if the
       upload happened more than the minimum days specified by the
       urgency of the upload; if this is not true, the package is
       ignored as `too-young'. Note that the urgency is sticky, meaning
       that the highest urgency uploaded since the previous testing
       transition is taken into account.

    8. If the suite is unstable, all the architecture-dependent binary
       packages and the architecture-independent ones for the `nobreakall'
       architectures have to be built from the source we are considering.
       If this is not true, then these are called `out-of-date'
       architectures and the package is ignored.

    9. The source package must have at least a binary package, otherwise
       it is ignored.

   10. If the suite is unstable, the new source package must have no
       release critical bugs which do not also apply to the testing
       one. If this is not true, the package is ignored as `buggy'.

   11. If there is a `force' hint for the source package, then it is
       updated even if it is marked as ignored from the previous steps.

   12. If the suite is testing-proposed-updates, the source package can
       be updated only if there is an explicit approval for it.  Unless
       a `force' hint exists, the new package must also be available
       on all of the architectures for which it has binary packages in
       testing.

   13. If the package will be ignored, mark it as "Valid candidate",
       otherwise mark it as "Not considered".

 * The list of `remove' hints is processed: if the requested source
   package is not already being updated or removed and the version
   actually in testing is the same specified with the `remove' hint,
   it is marked for removal.

 * The excuses are sorted by the number of days from the last upload
   (days-old) and by name.

 * A list of unconsidered excuses (for which the package is not upgraded)
   is built. Using this list, all the excuses depending on them is marked
   as invalid for "unpossible dependency".

 * The excuses are written in an HTML file.
"""

import os
import re
import sys
import string
import time
import copy
import optparse
import operator
import urllib

import apt_pkg

from excuse import Excuse
from britney import buildSystem

__author__ = 'Fabio Tranchitella'
__version__ = '2.0.alpha1'

# source package
VERSION = 0
SECTION = 1
BINARIES = 2
MAINTAINER = 3
FAKESRC = 4

# binary package
SOURCE = 2
SOURCEVER = 3
ARCHITECTURE = 4
PREDEPENDS = 5
DEPENDS = 6
CONFLICTS = 7
PROVIDES = 8
RDEPENDS = 9
RCONFLICTS = 10


class Britney:
    """Britney, the Debian testing updater script
    
    This is the script that updates the testing distribution. It is executed
    each day after the installation of the updated packages. It generates the 
    `Packages' files for the testing distribution, but it does so in an
    intelligent manner; it tries to avoid any inconsistency and to use only
    non-buggy packages.

    For more documentation on this script, please read the Developers Reference.
    """

    HINTS_HELPERS = ("easy", "hint", "remove", "block", "block-udeb", "unblock", "unblock-udeb", "approve")
    HINTS_STANDARD = ("urgent", "age-days") + HINTS_HELPERS
    HINTS_ALL = ("force", "force-hint", "block-all") + HINTS_STANDARD

    def __init__(self):
        """Class constructor

        This method initializes and populates the data lists, which contain all
        the information needed by the other methods of the class.
        """
        self.date_now = int(((time.time() / (60*60)) - 15) / 24)

        # parse the command line arguments
        self.__parse_arguments()

        # initialize the apt_pkg back-end
        apt_pkg.init()
        self.systems = {}

        # if requested, build the non-installable status and save it
        # if this or the population of self.binaries below takes a very
        # long time, try increasing SIZEOFHASHMAP in lib/dpkg.c and rebuilding
        if not self.options.nuninst_cache:
            self.__log("Building the list of non-installable packages for the full archive", type="I")
            self.sources = {'testing': self.read_sources(self.options.testing)}
            nuninst = {}
            for arch in self.options.architectures:
                self.binaries = {'testing': {arch: self.read_binaries(self.options.testing, "testing", arch)}}
                self.build_systems(arch)
                self.__log("> Checking for non-installable packages for architecture %s" % arch, type="I")
                result = self.get_nuninst(arch, build=True)
                nuninst.update(result)
                self.__log("> Found %d non-installable packages" % len(nuninst[arch]), type="I")
                if self.options.print_uninst:
                    self.nuninst_arch_report(nuninst, arch)
            if not self.options.print_uninst:
                self.write_nuninst(nuninst)
        else:
            self.__log("Not building the list of non-installable packages, as requested", type="I")

        # if running in --print-uninst mode, quit here
        if self.options.print_uninst:
            print '* summary'
            print '\n'.join(map(lambda x: '%4d %s' % (len(nuninst[x]), x), self.options.architectures))
            return

        # read the source and binary packages for the involved distributions
        # if this takes a very long time, try increasing SIZEOFHASHMAP in
        # lib/dpkg.c and rebuilding
        self.sources = {'testing': self.read_sources(self.options.testing),
                        'unstable': self.read_sources(self.options.unstable),
                        'tpu': self.read_sources(self.options.tpu),}
        self.binaries = {'testing': {}, 'unstable': {}, 'tpu': {}}
        for arch in self.options.architectures:
            self.binaries['testing'][arch] = self.read_binaries(self.options.testing, "testing", arch)
            self.binaries['unstable'][arch] = self.read_binaries(self.options.unstable, "unstable", arch)
            self.binaries['tpu'][arch] = self.read_binaries(self.options.tpu, "tpu", arch)
            # build the testing system
            self.build_systems(arch)

        # read the release-critical bug summaries for testing and unstable
        self.bugs = {'unstable': self.read_bugs(self.options.unstable),
                     'testing': self.read_bugs(self.options.testing),}
        self.normalize_bugs()

        # read additional data
        self.dates = self.read_dates(self.options.testing)
        self.urgencies = self.read_urgencies(self.options.testing)
        self.hints = self.read_hints(self.options.unstable)
        self.excuses = []
        self.dependencies = {}

    def __parse_arguments(self):
        """Parse the command line arguments

        This method parses and initializes the command line arguments.
        While doing so, it preprocesses some of the options to be converted
        in a suitable form for the other methods of the class.
        """
        # initialize the parser
        self.parser = optparse.OptionParser(version="%prog")
        self.parser.add_option("-v", "", action="count", dest="verbose", help="enable verbose output")
        self.parser.add_option("-c", "--config", action="store", dest="config", default="/etc/britney.conf",
                               help="path for the configuration file")
        self.parser.add_option("", "--architectures", action="store", dest="architectures", default=None,
                               help="override architectures from configuration file")
        self.parser.add_option("", "--actions", action="store", dest="actions", default=None,
                               help="override the list of actions to be performed")
        self.parser.add_option("", "--hints", action="store", dest="hints", default=None,
                               help="additional hints, separated by semicolons")
        self.parser.add_option("", "--hint-tester", action="store_true", dest="hint_tester", default=None,
                               help="provide a command line interface to test hints")
        self.parser.add_option("", "--dry-run", action="store_true", dest="dry_run", default=False,
                               help="disable all outputs to the testing directory")
        self.parser.add_option("", "--compatible", action="store_true", dest="compatible", default=False,
                               help="enable full compatibility with old britney's output")
        self.parser.add_option("", "--auto-hinter", action="store_true", dest="autohinter", default=False,
                               help="enable use of auto-hinter")
        self.parser.add_option("", "--control-files", action="store_true", dest="control_files", default=False,
                               help="enable control files generation")
        self.parser.add_option("", "--nuninst-cache", action="store_true", dest="nuninst_cache", default=False,
                               help="do not build the non-installability status, use the cache from file")
        self.parser.add_option("", "--print-uninst", action="store_true", dest="print_uninst", default=False,
                               help="just print a summary of uninstallable packages")
        (self.options, self.args) = self.parser.parse_args()
        
        # integrity checks
        if self.options.nuninst_cache and self.options.print_uninst:
            exit.__log("nuninst_cache and print_uninst are mutually exclusive!", type="E")
            sys.exit(1)
        # if the configuration file exists, than read it and set the additional options
        elif not os.path.isfile(self.options.config):
            self.__log("Unable to read the configuration file (%s), exiting!" % self.options.config, type="E")
            sys.exit(1)

        # minimum days for unstable-testing transition and the list of hints
        # are handled as an ad-hoc case
        self.MINDAYS = {}
        self.HINTS = {'command-line': self.HINTS_ALL}
        for k, v in [map(string.strip,r.split('=', 1)) for r in file(self.options.config) if '=' in r and not r.strip().startswith('#')]:
            if k.startswith("MINDAYS_"):
                self.MINDAYS[k.split("_")[1].lower()] = int(v)
            elif k.startswith("HINTS_"):
                self.HINTS[k.split("_")[1].lower()] = \
                    reduce(lambda x,y: x+y, [hasattr(self, "HINTS_" + i) and getattr(self, "HINTS_" + i) or (i,) for i in v.split()])
            elif not hasattr(self.options, k.lower()) or \
                 not getattr(self.options, k.lower()):
                setattr(self.options, k.lower(), v)

        # Sort the architecture list
        allarches = sorted(self.options.architectures.split())
        arches = [x for x in allarches if x in self.options.nobreakall_arches.split()]
        arches += [x for x in allarches if x not in arches and x not in self.options.fucked_arches.split()]
        arches += [x for x in allarches if x not in arches and x not in self.options.break_arches.split()]
        arches += [x for x in allarches if x not in arches and x not in self.options.new_arches.split()]
        arches += [x for x in allarches if x not in arches]
        self.options.architectures = arches
        self.options.smooth_updates = self.options.smooth_updates.split()

    def __log(self, msg, type="I"):
        """Print info messages according to verbosity level
        
        An easy-and-simple log method which prints messages to the standard
        output. The type parameter controls the urgency of the message, and
        can be equal to `I' for `Information', `W' for `Warning' and `E' for
        `Error'. Warnings and errors are always printed, and information is
        printed only if the verbose logging is enabled.
        """
        if self.options.verbose or type in ("E", "W"):
            print "%s: [%s] - %s" % (type, time.asctime(), msg)

    # Data reading/writing methods
    # ----------------------------

    def build_systems(self, arch=None):
        for a in self.options.architectures:
            if arch and a != arch: continue
            packages = {}
            binaries = self.binaries['testing'][arch][0].copy()
            for k in binaries:
                packages[k] = binaries[k][:]
                if packages[k][PROVIDES]:
                    packages[k][PROVIDES] = ", ".join(packages[k][PROVIDES])
                else: packages[k][PROVIDES] = None
            self.systems[a] = buildSystem(a, packages)

    def read_sources(self, basedir):
        """Read the list of source packages from the specified directory
        
        The source packages are read from the `Sources' file within the
        directory specified as `basedir' parameter. Considering the
        large amount of memory needed, not all the fields are loaded
        in memory. The available fields are Version, Maintainer and Section.

        The method returns a list where every item represents a source
        package as a dictionary.
        """
        sources = {}
        package = None
        filename = os.path.join(basedir, "Sources")
        self.__log("Loading source packages from %s" % filename)
        try:
            Packages = apt_pkg.TagFile(open(filename))
            get_field = Packages.section.get
            step = Packages.step
        except AttributeError, e:
            Packages = apt_pkg.ParseTagFile(open(filename))
            get_field = Packages.Section.get
            step = Packages.Step
        while step():
            pkg = get_field('Package')
            ver = get_field('Version')
            # There may be multiple versions of the source package
            # (in unstable) if some architectures have out-of-date
            # binaries.  We only ever consider the source with the
            # largest version for migration.
            if pkg in sources and apt_pkg.VersionCompare(sources[pkg][0], ver) > 0:
                continue
            sources[pkg] = [ver,
                            get_field('Section'),
                            [],
                            get_field('Maintainer'),
                            False,
                           ]
        return sources

    def read_binaries(self, basedir, distribution, arch):
        """Read the list of binary packages from the specified directory
        
        The binary packages are read from the `Packages_${arch}' files
        within the directory specified as `basedir' parameter, replacing
        ${arch} with the value of the arch parameter. Considering the
        large amount of memory needed, not all the fields are loaded
        in memory. The available fields are Version, Source, Pre-Depends,
        Depends, Conflicts, Provides and Architecture.
        
        After reading the packages, reverse dependencies are computed
        and saved in the `rdepends' keys, and the `Provides' field is
        used to populate the virtual packages list.

        The dependencies are parsed with the apt.pkg.ParseDepends method,
        and they are stored both as the format of its return value and
        text.

        The method returns a tuple. The first element is a list where
        every item represents a binary package as a dictionary; the second
        element is a dictionary which maps virtual packages to real
        packages that provide them.
        """

        packages = {}
        provides = {}
        sources = self.sources
        package = None

        filename = os.path.join(basedir, "Packages_%s" % arch)
        self.__log("Loading binary packages from %s" % filename)
        try:
            Packages = apt_pkg.TagFile(open(filename))
            get_field = Packages.section.get
            step = Packages.step
        except AttributeError, e:
            Packages = apt_pkg.ParseTagFile(open(filename))
            get_field = Packages.Section.get
            step = Packages.Step
        while step():
            pkg = get_field('Package')
            version = get_field('Version')

            # There may be multiple versions of any arch:all packages
            # (in unstable) if some architectures have out-of-date
            # binaries.  We only ever consider the package with the
            # largest version for migration.
            if pkg in packages and apt_pkg.VersionCompare(packages[pkg][0], version) > 0:
                continue

            final_conflicts_list = []
            conflicts = get_field('Conflicts')
            if conflicts:
                final_conflicts_list.append(conflicts)
            breaks = get_field('Breaks')
            if breaks:
                final_conflicts_list.append(breaks)
            dpkg = [version,
                    get_field('Section'),
                    pkg, 
                    version,
                    get_field('Architecture'),
                    get_field('Pre-Depends'),
                    get_field('Depends'),
                    ', '.join(final_conflicts_list) or None,
                    get_field('Provides'),
                    [],
                    [],
                   ]

            # retrieve the name and the version of the source package
            source = get_field('Source')
            if source:
                dpkg[SOURCE] = source.split(" ")[0]
                if "(" in source:
                    dpkg[SOURCEVER] = source[source.find("(")+1:source.find(")")]

            # if the source package is available in the distribution, then register this binary package
            if dpkg[SOURCE] in sources[distribution]:
                sources[distribution][dpkg[SOURCE]][BINARIES].append(pkg + "/" + arch)
            # if the source package doesn't exist, create a fake one
            else:
                sources[distribution][dpkg[SOURCE]] = [dpkg[SOURCEVER], None, [pkg + "/" + arch], None, True]

            # register virtual packages and real packages that provide them
            if dpkg[PROVIDES]:
                parts = map(string.strip, dpkg[PROVIDES].split(","))
                for p in parts:
                    if p not in provides:
                        provides[p] = []
                    provides[p].append(pkg)
                dpkg[PROVIDES] = parts
            else: dpkg[PROVIDES] = []

            # add the resulting dictionary to the package list
            packages[pkg] = dpkg

        # loop again on the list of packages to register reverse dependencies and conflicts
        register_reverses = self.register_reverses
        for pkg in packages:
            register_reverses(pkg, packages, provides, check_doubles=False)

        # return a tuple with the list of real and virtual packages
        return (packages, provides)

    def register_reverses(self, pkg, packages, provides, check_doubles=True, parse_depends=apt_pkg.ParseDepends):
        """Register reverse dependencies and conflicts for the specified package

        This method register the reverse dependencies and conflicts for
        a give package using `packages` as list of packages and `provides`
        as list of virtual packages.

        The method has an optional parameter parse_depends which is there
        just for performance reasons and is not meant to be overwritten.
        """
        # register the list of the dependencies for the depending packages
        dependencies = []
        if packages[pkg][DEPENDS]:
            dependencies.extend(parse_depends(packages[pkg][DEPENDS]))
        if packages[pkg][PREDEPENDS]:
            dependencies.extend(parse_depends(packages[pkg][PREDEPENDS]))
        # go through the list
        for p in dependencies:
            for a in p:
                # register real packages
                if a[0] in packages and (not check_doubles or pkg not in packages[a[0]][RDEPENDS]):
                    packages[a[0]][RDEPENDS].append(pkg)
                # register packages which provide a virtual package
                elif a[0] in provides:
                    for i in provides.get(a[0]):
                        if i not in packages: continue
                        if not check_doubles or pkg not in packages[i][RDEPENDS]:
                            packages[i][RDEPENDS].append(pkg)
        # register the list of the conflicts for the conflicting packages
        if packages[pkg][CONFLICTS]:
            for p in parse_depends(packages[pkg][CONFLICTS]):
                for a in p:
                    # register real packages
                    if a[0] in packages and (not check_doubles or pkg not in packages[a[0]][RCONFLICTS]):
                        packages[a[0]][RCONFLICTS].append(pkg)
                    # register packages which provides a virtual package
                    elif a[0] in provides:
                        for i in provides[a[0]]:
                            if i not in packages: continue
                            if not check_doubles or pkg not in packages[i][RCONFLICTS]:
                                packages[i][RCONFLICTS].append(pkg)
     
    def read_bugs(self, basedir):
        """Read the release critial bug summary from the specified directory
        
        The RC bug summaries are read from the `BugsV' file within the
        directory specified as `basedir' parameter. The file contains
        rows with the format:

        <package-name> <bug number>[,<bug number>...]

        The method returns a dictionary where the key is the binary package
        name and the value is the list of open RC bugs for it.
        """
        bugs = {}
        filename = os.path.join(basedir, "BugsV")
        self.__log("Loading RC bugs data from %s" % filename)
        for line in open(filename):
            l = line.split()
            if len(l) != 2:
                self.__log("Malformed line found in line %s" % (line), type='W')
                continue
            pkg = l[0]
            bugs.setdefault(pkg, [])
            bugs[pkg] += l[1].split(",")
        return bugs

    def write_bugs(self, basedir, bugs):
        """Write the release critical bug summary to the specified directory

        For a more detailed explanation of the format, please check the method
        read_bugs.
        """
        filename = os.path.join(basedir, "BugsV")
        self.__log("Writing RC bugs data to %s" % filename)
        f = open(filename, 'w')
        for pkg in sorted(bugs.keys()):
            if not bugs[pkg]:
                continue
            f.write("%s %s\n" % (pkg, ','.join(bugs[pkg])))
        f.close()

    def __maxver(self, pkg, dist):
        """Return the maximum version for a given package name
        
        This method returns None if the specified source package
        is not available in the `dist' distribution. If the package
        exists, then it returns the maximum version between the
        source package and its binary packages.
        """
        maxver = None
        if pkg in self.sources[dist]:
            maxver = self.sources[dist][pkg][VERSION]
        for arch in self.options.architectures:
            if pkg not in self.binaries[dist][arch][0]: continue
            pkgv = self.binaries[dist][arch][0][pkg][VERSION]
            if maxver == None or apt_pkg.VersionCompare(pkgv, maxver) > 0:
                maxver = pkgv
        return maxver

    def normalize_bugs(self):
        """Normalize the release critical bug summaries for testing and unstable
        
        The method doesn't return any value: it directly modifies the
        object attribute `bugs'.
        """
        # loop on all the package names from testing and unstable bug summaries
        for pkg in set(self.bugs['testing'].keys() + self.bugs['unstable'].keys()):

            # make sure that the key is present in both dictionaries
            if pkg not in self.bugs['testing']:
                self.bugs['testing'][pkg] = []
            elif pkg not in self.bugs['unstable']:
                self.bugs['unstable'][pkg] = []

            if pkg.startswith("src:"):
                pkg = pkg[4:]

            # retrieve the maximum version of the package in testing:
            maxvert = self.__maxver(pkg, 'testing')

            # if the package is not available in testing, then reset
            # the list of RC bugs
            if maxvert == None:
                self.bugs['testing'][pkg] = []

    def read_dates(self, basedir):
        """Read the upload date for the packages from the specified directory
        
        The upload dates are read from the `Date' file within the directory
        specified as `basedir' parameter. The file contains rows with the
        format:

        <package-name> <version> <date-of-upload>

        The dates are expressed as days starting from the 1970-01-01.

        The method returns a dictionary where the key is the binary package
        name and the value is tuple with two items, the version and the date.
        """
        dates = {}
        filename = os.path.join(basedir, "Dates")
        self.__log("Loading upload data from %s" % filename)
        for line in open(filename):
            l = line.split()
            if len(l) != 3: continue
            try:
                dates[l[0]] = (l[1], int(l[2]))
            except ValueError:
                self.__log("Dates, unable to parse \"%s\"" % line, type="E")
        return dates

    def write_dates(self, basedir, dates):
        """Write the upload date for the packages to the specified directory

        For a more detailed explanation of the format, please check the method
        read_dates.
        """
        filename = os.path.join(basedir, "Dates")
        self.__log("Writing upload data to %s" % filename)
        f = open(filename, 'w')
        for pkg in sorted(dates.keys()):
            f.write("%s %s %d\n" % ((pkg,) + dates[pkg]))
        f.close()


    def read_urgencies(self, basedir):
        """Read the upload urgency of the packages from the specified directory
        
        The upload urgencies are read from the `Urgency' file within the
        directory specified as `basedir' parameter. The file contains rows
        with the format:

        <package-name> <version> <urgency>

        The method returns a dictionary where the key is the binary package
        name and the value is the greatest urgency from the versions of the
        package that are higher then the testing one.
        """

        urgencies = {}
        filename = os.path.join(basedir, "Urgency")
        self.__log("Loading upload urgencies from %s" % filename)
        for line in open(filename):
            l = line.split()
            if len(l) != 3: continue

            # read the minimum days associated with the urgencies
            urgency_old = urgencies.get(l[0], self.options.default_urgency)
            mindays_old = self.MINDAYS.get(urgency_old, self.MINDAYS[self.options.default_urgency])
            mindays_new = self.MINDAYS.get(l[2], self.MINDAYS[self.options.default_urgency])

            # if the new urgency is lower (so the min days are higher), do nothing
            if mindays_old <= mindays_new:
                continue

            # if the package exists in testing and it is more recent, do nothing
            tsrcv = self.sources['testing'].get(l[0], None)
            if tsrcv and apt_pkg.VersionCompare(tsrcv[VERSION], l[1]) >= 0:
                continue

            # if the package doesn't exist in unstable or it is older, do nothing
            usrcv = self.sources['unstable'].get(l[0], None)
            if not usrcv or apt_pkg.VersionCompare(usrcv[VERSION], l[1]) < 0:
                continue

            # update the urgency for the package
            urgencies[l[0]] = l[2]

        return urgencies

    def read_hints(self, basedir):
        """Read the hint commands from the specified directory
        
        The hint commands are read from the files contained in the `Hints'
        directory within the directory specified as `basedir' parameter. 
        The names of the files have to be the same as the authorized users
        for the hints.
        
        The file contains rows with the format:

        <command> <package-name>[/<version>]

        The method returns a dictionary where the key is the command, and
        the value is the list of affected packages.
        """
        hints = dict([(k,[]) for k in self.HINTS_ALL])

        for who in self.HINTS.keys():
            if who == 'command-line':
                lines = self.options.hints and self.options.hints.split(';') or ()
            else:
                filename = os.path.join(basedir, "Hints", who)
                if not os.path.isfile(filename):
                    self.__log("Cannot read hints list from %s, no such file!" % filename, type="E")
                    continue
                self.__log("Loading hints list from %s" % filename)
                lines = open(filename)
            for line in lines:
                line = line.strip()
                if line == "": continue
                l = line.split()
                if l[0] == 'finished':
                    break
                elif l[0] not in self.HINTS[who]:
                    continue
                elif l[0] in ["easy", "hint", "force-hint"]:
                    hints[l[0]].append((who, [k.rsplit("/", 1) for k in l if "/" in k]))
                elif l[0] in ["block-all"]:
                    hints[l[0]].extend([(y, who) for y in l[1:]])
                elif l[0] in ["block", "block-udeb"]:
                    hints[l[0]].extend([(y, who) for y in l[1:]])
                elif l[0] in ["age-days"] and len(l) >= 3 and l[1].isdigit():
                    days = l[1]
                    tmp = [tuple([who] + k.rsplit("/", 1)) for k in l[2:] if "/" in k]
                    hints[l[0]].extend([(p, (v, h, days)) for h, p, v in tmp])
                elif l[0] in ["remove", "approve", "unblock", "unblock-udeb", "force", "urgent"]:
                    hints[l[0]].extend([(k.rsplit("/", 1)[0], (k.rsplit("/", 1)[1], who)) for k in l if "/" in k])

        for x in ["approve", "block", "block-all", "block-udeb", "unblock", "unblock-udeb", "force", "urgent", "remove", "age-days"]:
            z = {}
            for a, b in hints[x]:
                if z.has_key(a) and z[a] != b:
                    if x in ['unblock', 'unblock-udeb']:
                        if apt_pkg.VersionCompare(z[a][0], b[0]) < 0:
                            # This hint is for a newer version, so discard the old one
                            self.__log("Overriding %s[%s] = %s with %s" % (x, a, z[a], b), type="W")
                        else:
                            # This hint is for an older version, so ignore the new one
                            self.__log("Ignoring %s[%s] = %s, %s is higher or equal" % (x, a, b, z[a]), type="W")
                            continue
                    else:
                        self.__log("Overriding %s[%s] = %s with %s" % (x, a, z[a], b), type="W")
                z[a] = b
            hints[x] = z

        # Sanity check the hints hash
        if len(hints["block"]) == 0 and len(hints["block-udeb"]) == 0:
            self.__log("WARNING: No block hints at all, not even udeb ones!", type="W")

        # A t-p-u approval overrides an unstable block
        for p in hints["approve"]:
            hints["unblock"][p] = hints["approve"][p]

        return hints

    def write_heidi(self, filename):
        """Write the output HeidiResult

        This method write the output for Heidi, which contains all the
        binary packages and the source packages in the form:
        
        <pkg-name> <pkg-version> <pkg-architecture> <pkg-section>
        <src-name> <src-version> <src-section>
        """
        self.__log("Writing Heidi results to %s" % filename)
        f = open(filename, 'w')

        # local copies
        sources = self.sources['testing']

        # write binary packages
        for arch in sorted(self.options.architectures):
            binaries = self.binaries['testing'][arch][0]
            for pkg_name in sorted(binaries):
                pkg = binaries[pkg_name]
                pkgv = pkg[VERSION]
                pkgarch = pkg[ARCHITECTURE] or 'all'
                pkgsec = pkg[SECTION] or 'faux'
                f.write('%s %s %s %s\n' % (pkg_name, pkgv, pkgarch, pkgsec))

        # write sources
        for src_name in sorted(sources):
            src = sources[src_name]
            srcv = src[VERSION]
            srcsec = src[FAKESRC] and 'faux' or src[SECTION] or 'unknown'
            f.write('%s %s source %s\n' % (src_name, srcv, srcsec))

        f.close()

    def write_controlfiles(self, basedir, suite):
        """Write the control files

        This method writes the control files for the binary packages of all
        the architectures and for the source packages.
        """
        sources = self.sources[suite]

        self.__log("Writing new %s control files to %s" % (suite, basedir))
        for arch in self.options.architectures:
            filename = os.path.join(basedir, 'Packages_%s' % arch)
            f = open(filename, 'w')
            binaries = self.binaries[suite][arch][0]
            for pkg in binaries:
                output = "Package: %s\n" % pkg
                for key, k in ((SECTION, 'Section'), (ARCHITECTURE, 'Architecture'), (SOURCE, 'Source'), (VERSION, 'Version'), 
                          (PREDEPENDS, 'Pre-Depends'), (DEPENDS, 'Depends'), (PROVIDES, 'Provides'), (CONFLICTS, 'Conflicts')):
                    if not binaries[pkg][key]: continue
                    if key == SOURCE:
                        if binaries[pkg][SOURCE] == pkg:
                            if binaries[pkg][SOURCEVER] != binaries[pkg][VERSION]:
                                source = binaries[pkg][SOURCE] + " (" + binaries[pkg][SOURCEVER] + ")"
                            else: continue
                        else:
                            if binaries[pkg][SOURCEVER] != binaries[pkg][VERSION]:
                                source = binaries[pkg][SOURCE] + " (" + binaries[pkg][SOURCEVER] + ")"
                            else:
                                source = binaries[pkg][SOURCE]
                        output += (k + ": " + source + "\n")
                        if sources[binaries[pkg][SOURCE]][MAINTAINER]:
                            output += ("Maintainer: " + sources[binaries[pkg][SOURCE]][MAINTAINER] + "\n")
                    elif key == PROVIDES:
                        if len(binaries[pkg][key]) > 0:
                            output += (k + ": " + ", ".join(binaries[pkg][key]) + "\n")
                    else:
                        output += (k + ": " + binaries[pkg][key] + "\n")
                f.write(output + "\n")
            f.close()

        filename = os.path.join(basedir, 'Sources')
        f = open(filename, 'w')
        for src in sources:
            output = "Package: %s\n" % src
            for key, k in ((VERSION, 'Version'), (SECTION, 'Section'), (MAINTAINER, 'Maintainer')):
                if not sources[src][key]: continue
                output += (k + ": " + sources[src][key] + "\n")
            f.write(output + "\n")
        f.close()

    def write_nuninst(self, nuninst):
        """Write the non-installable report"""
        f = open(self.options.noninst_status, 'w')
        f.write("Built on: " + time.strftime("%Y.%m.%d %H:%M:%S %z", time.gmtime(time.time())) + "\n")
        f.write("Last update: " + time.strftime("%Y.%m.%d %H:%M:%S %z", time.gmtime(time.time())) + "\n\n")
        f.write("".join([k + ": " + " ".join(nuninst[k]) + "\n" for k in nuninst]))
        f.close()

    def read_nuninst(self):
        """Read the non-installable report"""
        f = open(self.options.noninst_status)
        nuninst = {}
        for r in f:
            if ":" not in r: continue
            arch, packages = r.strip().split(":", 1)
            if arch.split("+", 1)[0] in self.options.architectures:
                nuninst[arch] = set(packages.split())
        return nuninst


    # Utility methods for package analisys
    # ------------------------------------

    def same_source(self, sv1, sv2):
        """Check if two version numbers are built from the same source

        This method returns a boolean value which is true if the two
        version numbers specified as parameters are built from the same
        source. The main use of this code is to detect binary-NMU.
        """
        if sv1 == sv2:
            return 1

        m = re.match(r'^(.*)\+b\d+$', sv1)
        if m: sv1 = m.group(1)
        m = re.match(r'^(.*)\+b\d+$', sv2)
        if m: sv2 = m.group(1)

        if sv1 == sv2:
            return 1

        return 0

    def get_dependency_solvers(self, block, arch, distribution, excluded=[], strict=False):
        """Find the packages which satisfy a dependency block

        This method returns the list of packages which satisfy a dependency
        block (as returned by apt_pkg.ParseDepends) for the given architecture
        and distribution.

        It returns a tuple with two items: the first is a boolean which is
        True if the dependency is satisfied, the second is the list of the
        solving packages.
        """

        packages = []

        # local copies for better performances
        binaries = self.binaries[distribution][arch]

        # for every package, version and operation in the block
        for name, version, op in block:
            # look for the package in unstable
            if name not in excluded and name in binaries[0]:
                package = binaries[0][name]
                # check the versioned dependency (if present)
                if op == '' and version == '' or apt_pkg.CheckDep(package[VERSION], op, version):
                    packages.append(name)

            # look for the package in the virtual packages list and loop on them
            for prov in binaries[1].get(name, []):
                if prov in excluded or \
                   prov not in binaries[0]: continue
                package = binaries[0][prov]
                # check the versioned dependency (if present)
                # TODO: this is forbidden by the debian policy, which says that versioned
                #       dependencies on virtual packages are never satisfied. The old britney
                #       does it and we have to go with it, but at least a warning should be raised.
                if op == '' and version == '' or not strict and apt_pkg.CheckDep(package[VERSION], op, version):
                    packages.append(prov)

        return (len(packages) > 0, packages)

    def excuse_unsat_deps(self, pkg, src, arch, suite, excuse, excluded=[], conflicts=False):
        """Find unsatisfied dependencies for a binary package

        This method analyzes the dependencies of the binary package specified
        by the parameter `pkg', built from the source package `src', for the
        architecture `arch' within the suite `suite'. If the dependency can't
        be satisfied in testing and/or unstable, it updates the excuse passed
        as parameter.

        The dependency fields checked are Pre-Depends and Depends.
        """
        # retrieve the binary package from the specified suite and arch
        binary_u = self.binaries[suite][arch][0][pkg]

        # local copies for better performances
        parse_depends = apt_pkg.ParseDepends
        get_dependency_solvers = self.get_dependency_solvers
        strict = True # not self.options.compatible

        # analyze the dependency fields (if present)
        for type_key, type in ((PREDEPENDS, 'Pre-Depends'), (DEPENDS, 'Depends')):
            if not binary_u[type_key]:
                continue

            # for every block of dependency (which is formed as conjunction of disconjunction)
            for block, block_txt in zip(parse_depends(binary_u[type_key]), binary_u[type_key].split(',')):
                # if the block is satisfied in testing, then skip the block
                solved, packages = get_dependency_solvers(block, arch, 'testing', excluded, strict=strict)
                if solved:
                    for p in packages:
                        if p not in self.binaries[suite][arch][0]: continue
                        excuse.add_sane_dep(self.binaries[suite][arch][0][p][SOURCE])
                    continue

                # check if the block can be satisfied in unstable, and list the solving packages
                solved, packages = get_dependency_solvers(block, arch, suite, [], strict=strict)
                packages = [self.binaries[suite][arch][0][p][SOURCE] for p in packages]

                # if the dependency can be satisfied by the same source package, skip the block:
                # obviously both binary packages will enter testing together
                if src in packages: continue

                # if no package can satisfy the dependency, add this information to the excuse
                if len(packages) == 0:
                    excuse.addhtml("%s/%s unsatisfiable %s: %s" % (pkg, arch, type, block_txt.strip()))
                    if arch not in self.options.break_arches.split():
                        excuse.add_unsat_dep(arch)
                    continue

                # for the solving packages, update the excuse to add the dependencies
                for p in packages:
                    if arch not in self.options.break_arches.split():
                        excuse.add_dep(p)
                    else:
                        excuse.add_break_dep(p, arch)

        return True

    # Package analysis methods
    # ------------------------

    def should_remove_source(self, pkg):
        """Check if a source package should be removed from testing
        
        This method checks if a source package should be removed from the
        testing distribution; this happens if the source package is not
        present in the unstable distribution anymore.

        It returns True if the package can be removed, False otherwise.
        In the former case, a new excuse is appended to the the object
        attribute excuses.
        """
        # if the source package is available in unstable, then do nothing
        if pkg in self.sources['unstable']:
            return False
        # otherwise, add a new excuse for its removal and return True
        src = self.sources['testing'][pkg]
        excuse = Excuse("-" + pkg)
        excuse.set_vers(src[VERSION], None)
        src[MAINTAINER] and excuse.set_maint(src[MAINTAINER].strip())
        src[SECTION] and excuse.set_section(src[SECTION].strip())

        # if the package is blocked, skip it
        if self.hints['block'].has_key('-' + pkg):
            excuse.addhtml("Not touching package, as requested by %s (contact debian-release "
                "if update is needed)" % self.hints['block']['-' + pkg])
            excuse.addhtml("Not considered")
            self.excuses.append(excuse)
            return False

        excuse.addhtml("Valid candidate")
        self.excuses.append(excuse)
        return True

    def should_upgrade_srcarch(self, src, arch, suite):
        """Check if a binary package should be upgraded

        This method checks if a binary package should be upgraded; this can
        happen also if the binary package is a binary-NMU for the given arch.
        The analysis is performed for the source package specified by the
        `src' parameter, checking the architecture `arch' for the distribution
        `suite'.
       
        It returns False if the given package doesn't need to be upgraded,
        True otherwise. In the former case, a new excuse is appended to
        the the object attribute excuses.
        """
        # retrieve the source packages for testing and suite
        source_t = self.sources['testing'][src]
        source_u = self.sources[suite][src]

        # build the common part of the excuse, which will be filled by the code below
        ref = "%s/%s%s" % (src, arch, suite != 'unstable' and "_" + suite or "")
        excuse = Excuse(ref)
        excuse.set_vers(source_t[VERSION], source_t[VERSION])
        source_u[MAINTAINER] and excuse.set_maint(source_u[MAINTAINER].strip())
        source_u[SECTION] and excuse.set_section(source_u[SECTION].strip())
        
        # if there is a `remove' hint and the requested version is the same as the
        # version in testing, then stop here and return False
        if src in self.hints["remove"] and \
           self.same_source(source_t[VERSION], self.hints["remove"][src][0]):
            excuse.addhtml("Removal request by %s" % (self.hints["remove"][src][1]))
            excuse.addhtml("Trying to remove package, not update it")
            excuse.addhtml("Not considered")
            self.excuses.append(excuse)
            return False

        # the starting point is that there is nothing wrong and nothing worth doing
        anywrongver = False
        anyworthdoing = False

        # for every binary package produced by this source in unstable for this architecture
        for pkg in sorted(filter(lambda x: x.endswith("/" + arch), source_u[BINARIES]), key=lambda x: x.split("/")[0]):
            pkg_name = pkg.split("/")[0]

            # retrieve the testing (if present) and unstable corresponding binary packages
            binary_t = pkg in source_t[BINARIES] and self.binaries['testing'][arch][0][pkg_name] or None
            binary_u = self.binaries[suite][arch][0][pkg_name]

            # this is the source version for the new binary package
            pkgsv = self.binaries[suite][arch][0][pkg_name][SOURCEVER]

            # if the new binary package is architecture-independent, then skip it
            if binary_u[ARCHITECTURE] == 'all':
                excuse.addhtml("Ignoring %s %s (from %s) as it is arch: all" % (pkg_name, binary_u[VERSION], pkgsv))
                continue

            # if the new binary package is not from the same source as the testing one, then skip it
            if not self.same_source(source_t[VERSION], pkgsv):
                anywrongver = True
                excuse.addhtml("From wrong source: %s %s (%s not %s)" % (pkg_name, binary_u[VERSION], pkgsv, source_t[VERSION]))
                break

            # find unsatisfied dependencies for the new binary package
            self.excuse_unsat_deps(pkg_name, src, arch, suite, excuse)

            # if the binary is not present in testing, then it is a new binary;
            # in this case, there is something worth doing
            if not binary_t:
                excuse.addhtml("New binary: %s (%s)" % (pkg_name, binary_u[VERSION]))
                anyworthdoing = True
                continue

            # at this point, the binary package is present in testing, so we can compare
            # the versions of the packages ...
            vcompare = apt_pkg.VersionCompare(binary_t[VERSION], binary_u[VERSION])

            # ... if updating would mean downgrading, then stop here: there is something wrong
            if vcompare > 0:
                anywrongver = True
                excuse.addhtml("Not downgrading: %s (%s to %s)" % (pkg_name, binary_t[VERSION], binary_u[VERSION]))
                break
            # ... if updating would mean upgrading, then there is something worth doing
            elif vcompare < 0:
                excuse.addhtml("Updated binary: %s (%s to %s)" % (pkg_name, binary_t[VERSION], binary_u[VERSION]))
                anyworthdoing = True

        # if there is nothing wrong and there is something worth doing or the source
        # package is not fake, then check what packages should be removed
        if not anywrongver and (anyworthdoing or not self.sources[suite][src][FAKESRC]):
            srcv = self.sources[suite][src][VERSION]
            ssrc = self.same_source(source_t[VERSION], srcv)
            # for every binary package produced by this source in testing for this architecture
            for pkg in sorted([x.split("/")[0] for x in self.sources['testing'][src][BINARIES] if x.endswith("/"+arch)]):
                # if the package is architecture-independent, then ignore it
                if self.binaries['testing'][arch][0][pkg][ARCHITECTURE] == 'all':
                    excuse.addhtml("Ignoring removal of %s as it is arch: all" % (pkg))
                    continue
                # if the package is not produced by the new source package, then remove it from testing
                if pkg not in self.binaries[suite][arch][0]:
                    tpkgv = self.binaries['testing'][arch][0][pkg][VERSION]
                    excuse.addhtml("Removed binary: %s %s" % (pkg, tpkgv))
                    if ssrc: anyworthdoing = True

        # if there is nothing wrong and there is something worth doing, this is a valid candidate
        if not anywrongver and anyworthdoing:
            excuse.addhtml("Valid candidate")
            self.excuses.append(excuse)
            return True
        # else if there is something worth doing (but something wrong, too) this package won't be considered
        elif anyworthdoing:
            excuse.addhtml("Not considered")
            self.excuses.append(excuse)

        # otherwise, return False
        return False

    def should_upgrade_src(self, src, suite):
        """Check if source package should be upgraded

        This method checks if a source package should be upgraded. The analysis
        is performed for the source package specified by the `src' parameter, 
        checking the architecture `arch' for the distribution `suite'.
       
        It returns False if the given package doesn't need to be upgraded,
        True otherwise. In the former case, a new excuse is appended to
        the the object attribute excuses.
        """

        # retrieve the source packages for testing (if available) and suite
        source_u = self.sources[suite][src]
        if src in self.sources['testing']:
            source_t = self.sources['testing'][src]
            # if testing and unstable have the same version, then this is a candidate for binary-NMUs only
            if apt_pkg.VersionCompare(source_t[VERSION], source_u[VERSION]) == 0:
                return False
        else:
            source_t = None

        # build the common part of the excuse, which will be filled by the code below
        ref = "%s%s" % (src, suite != 'unstable' and "_" + suite or "")
        excuse = Excuse(ref)
        excuse.set_vers(source_t and source_t[VERSION] or None, source_u[VERSION])
        source_u[MAINTAINER] and excuse.set_maint(source_u[MAINTAINER].strip())
        source_u[SECTION] and excuse.set_section(source_u[SECTION].strip())

        # the starting point is that we will update the candidate
        update_candidate = True
        
        # if the version in unstable is older, then stop here with a warning in the excuse and return False
        if source_t and apt_pkg.VersionCompare(source_u[VERSION], source_t[VERSION]) < 0:
            excuse.addhtml("ALERT: %s is newer in testing (%s %s)" % (src, source_t[VERSION], source_u[VERSION]))
            self.excuses.append(excuse)
            return False

        # check if the source package really exists or if it is a fake one
        if source_u[FAKESRC]:
            excuse.addhtml("%s source package doesn't exist" % (src))
            update_candidate = False

        # retrieve the urgency for the upload, ignoring it if this is a NEW package (not present in testing)
        urgency = self.urgencies.get(src, self.options.default_urgency)
        if not source_t and urgency != self.options.default_urgency:
            excuse.addhtml("Ignoring %s urgency setting for NEW package" % (urgency))
            urgency = self.options.default_urgency

        # if there is a `remove' hint and the requested version is the same as the
        # version in testing, then stop here and return False
        if src in self.hints["remove"]:
            if source_t and self.same_source(source_t[VERSION], self.hints['remove'][src][0]) or \
               self.same_source(source_u[VERSION], self.hints['remove'][src][0]):
                excuse.addhtml("Removal request by %s" % (self.hints["remove"][src][1]))
                excuse.addhtml("Trying to remove package, not update it")
                update_candidate = False

        # check if there is a `block' or `block-udeb' hint for this package, or a `block-all source' hint
        blocked = {}
        if src in self.hints["block"]:
            blocked["block"] = self.hints["block"][src]
        elif 'source' in self.hints["block-all"]:
            blocked["block"] = self.hints["block-all"]["source"]

        if src in self.hints["block-udeb"]:
            blocked["block-udeb"] = self.hints["block-udeb"][src]

        # if the source is blocked, then look for an `unblock' hint; the unblock request
        # is processed only if the specified version is correct. If a package is blocked
        # by `block-udeb', then `unblock-udeb' must be present to cancel it.
        for block_cmd in blocked:
            unblock_cmd = "un" + block_cmd
            unblock = self.hints[unblock_cmd].get(src,(None,None))
            if unblock[0] != None and self.same_source(unblock[0], source_u[VERSION]):
                excuse.addhtml("Ignoring %s request by %s, due to %s request by %s" %
                               (block_cmd, blocked[block_cmd], unblock_cmd, self.hints[unblock_cmd][src][1]))
            else:
                if unblock[0] != None:
                    excuse.addhtml("%s request by %s ignored due to version mismatch: %s" %
                                   (unblock_cmd.capitalize(), self.hints[unblock_cmd][src][1], self.hints[unblock_cmd][src][0]))
                excuse.addhtml("Not touching package due to %s request by %s (contact debian-release if update is needed)" %
                               (block_cmd, blocked[block_cmd]))
                update_candidate = False

        # if the suite is unstable, then we have to check the urgency and the minimum days of
        # permanence in unstable before updating testing; if the source package is too young,
        # the check fails and we set update_candidate to False to block the update; consider
        # the age-days hint, if specified for the package
        if suite == 'unstable':
            if src not in self.dates:
                self.dates[src] = (source_u[VERSION], self.date_now)
            elif not self.same_source(self.dates[src][0], source_u[VERSION]):
                self.dates[src] = (source_u[VERSION], self.date_now)

            days_old = self.date_now - self.dates[src][1]
            min_days = self.MINDAYS[urgency]

            age_days_hint = self.hints["age-days"].get(src)
            if age_days_hint is not None and (age_days_hint[0] == "-" or \
               self.same_source(source_u[VERSION], age_days_hint[0])):
                excuse.addhtml("Overriding age needed from %d days to %d by %s" % (min_days,
                    int(self.hints["age-days"][src][2]), self.hints["age-days"][src][1]))
                min_days = int(self.hints["age-days"][src][2])

            excuse.setdaysold(days_old, min_days)
            if days_old < min_days:
                if src in self.hints["urgent"] and self.same_source(source_u[VERSION], self.hints["urgent"][src][0]):
                    excuse.addhtml("Too young, but urgency pushed by %s" % (self.hints["urgent"][src][1]))
                else:
                    update_candidate = False

        if suite == 'tpu':
            # o-o-d(ish) checks for t-p-u
            for arch in self.options.architectures:
                # If the package isn't in testing or the testing
                # package produces no packages on this architecture,
                # then it can't be out-of-date.  We assume that if
                # the t-p-u package has produced any binaries for
                # this architecture then it is ok

                if not src in self.sources["testing"] or \
                   (len([x for x in self.sources["testing"][src][BINARIES] if x.endswith("/"+arch) and self.binaries["testing"][arch][0][x.split("/")[0]][ARCHITECTURE] != 'all' ]) == 0) or \
                   (len([x for x in self.sources[suite][src][BINARIES] if x.endswith("/"+arch) and self.binaries[suite][arch][0][x.split("/")[0]][ARCHITECTURE] != 'all' ]) > 0):
                    continue

                text = "Not yet built on <a href=\"http://buildd.debian.org/status/logs.php?arch=%s&pkg=%s&ver=%s&suite=testing\" target=\"_blank\">%s</a> (relative to testing)" % (urllib.quote(arch), urllib.quote(src), urllib.quote(source_u[VERSION]), arch)

                if arch in self.options.fucked_arches.split():
                    text = text + " (but %s isn't keeping up, so never mind)" % (arch)
                else:
                    update_candidate = False

                excuse.addhtml(text)

        # at this point, we check the status of the builds on all the supported architectures
        # to catch the out-of-date ones
        pkgs = {src: ["source"]}
        for arch in self.options.architectures:
            oodbins = {}
            # for every binary package produced by this source in the suite for this architecture
            for pkg in sorted([x.split("/")[0] for x in self.sources[suite][src][BINARIES] if x.endswith("/"+arch)]):
                if pkg not in pkgs: pkgs[pkg] = []
                pkgs[pkg].append(arch)

                # retrieve the binary package and its source version
                binary_u = self.binaries[suite][arch][0][pkg]
                pkgsv = binary_u[SOURCEVER]

                # if it wasn't built by the same source, it is out-of-date
                if not self.same_source(source_u[VERSION], pkgsv):
                    if pkgsv not in oodbins:
                        oodbins[pkgsv] = []
                    oodbins[pkgsv].append(pkg)
                    continue

                # if the package is architecture-dependent or the current arch is `nobreakall'
                # find unsatisfied dependencies for the binary package
                if binary_u[ARCHITECTURE] != 'all' or arch in self.options.nobreakall_arches.split():
                    self.excuse_unsat_deps(pkg, src, arch, suite, excuse)

            # if there are out-of-date packages, warn about them in the excuse and set update_candidate
            # to False to block the update; if the architecture where the package is out-of-date is
            # in the `fucked_arches' list, then do not block the update
            if oodbins:
                oodtxt = ""
                for v in oodbins.keys():
                    if oodtxt: oodtxt = oodtxt + "; "
                    oodtxt = oodtxt + "%s (from <a href=\"http://buildd.debian.org/status/logs.php?" \
                        "arch=%s&pkg=%s&ver=%s\" target=\"_blank\">%s</a>)" % \
                        (", ".join(sorted(oodbins[v])), urllib.quote(arch), urllib.quote(src), urllib.quote(v), v)
                text = "out of date on <a href=\"http://buildd.debian.org/status/logs.php?" \
                    "arch=%s&pkg=%s&ver=%s\" target=\"_blank\">%s</a>: %s" % \
                    (urllib.quote(arch), urllib.quote(src), urllib.quote(source_u[VERSION]), arch, oodtxt)

                if arch in self.options.fucked_arches.split():
                    text = text + " (but %s isn't keeping up, so nevermind)" % (arch)
                else:
                    update_candidate = False

                if self.date_now != self.dates[src][1]:
                    excuse.addhtml(text)

        # if the source package has no binaries, set update_candidate to False to block the update
        if len(self.sources[suite][src][BINARIES]) == 0:
            excuse.addhtml("%s has no binaries on any arch" % src)
            update_candidate = False

        # if the suite is unstable, then we have to check the release-critical bug lists before
        # updating testing; if the unstable package has RC bugs that do not apply to the testing
        # one,  the check fails and we set update_candidate to False to block the update
        if suite == 'unstable':
            for pkg in pkgs.keys():
                bugs_t = []
                bugs_u = []
                if self.bugs['testing'].has_key(pkg):
                    bugs_t.extend(self.bugs['testing'][pkg])
                if self.bugs['unstable'].has_key(pkg):
                    bugs_u.extend(self.bugs['unstable'][pkg])
                if 'source' in pkgs[pkg]:
                    spkg = "src:%s" % (pkg)
                    if self.bugs['testing'].has_key(spkg):
                        bugs_t.extend(self.bugs['testing'][spkg])
                    if self.bugs['unstable'].has_key(spkg):
                        bugs_u.extend(self.bugs['unstable'][spkg])
 
                new_bugs = sorted(set(bugs_u).difference(bugs_t))
                old_bugs = sorted(set(bugs_t).difference(bugs_u))

                if len(new_bugs) > 0:
                    excuse.addhtml("%s (%s) <a href=\"http://bugs.debian.org/cgi-bin/pkgreport.cgi?" \
                        "which=pkg&data=%s&sev-inc=critical&sev-inc=grave&sev-inc=serious\" " \
                        "target=\"_blank\">has new bugs</a>!" % (pkg, ", ".join(pkgs[pkg]), urllib.quote(pkg)))
                    excuse.addhtml("Updating %s introduces new bugs: %s" % (pkg, ", ".join(
                        ["<a href=\"http://bugs.debian.org/%s\">#%s</a>" % (urllib.quote(a), a) for a in new_bugs])))
                    update_candidate = False

                if len(old_bugs) > 0:
                    excuse.addhtml("Updating %s fixes old bugs: %s" % (pkg, ", ".join(
                        ["<a href=\"http://bugs.debian.org/%s\">#%s</a>" % (urllib.quote(a), a) for a in old_bugs])))
                if len(old_bugs) > len(new_bugs) and len(new_bugs) > 0:
                    excuse.addhtml("%s introduces new bugs, so still ignored (even "
                        "though it fixes more than it introduces, whine at debian-release)" % pkg)

        # check if there is a `force' hint for this package, which allows it to go in even if it is not updateable
        if src in self.hints["force"] and self.same_source(source_u[VERSION], self.hints["force"][src][0]):
            excuse.dontinvalidate = 1
        if not update_candidate and src in self.hints["force"] and \
           self.same_source(source_u[VERSION], self.hints["force"][src][0]):
            excuse.addhtml("Should ignore, but forced by %s" % (self.hints["force"][src][1]))
            update_candidate = True

        # if the suite is testing-proposed-updates, the package needs an explicit approval in order to go in
        if suite == "tpu":
            key = "%s_%s" % (src, source_u[VERSION])
            if src in self.hints["approve"] and \
               self.same_source(source_u[VERSION], self.hints["approve"][src][0]):
                excuse.addhtml("Approved by %s" % self.hints["approve"][src][1])
            else:
                excuse.addhtml("NEEDS APPROVAL BY RM")
                update_candidate = False

        # if the package can be updated, it is a valid candidate
        if update_candidate:
            excuse.addhtml("Valid candidate")
        # else it won't be considered
        else:
            excuse.addhtml("Not considered")

        self.excuses.append(excuse)
        return update_candidate

    def reversed_exc_deps(self):
        """Reverse the excuses dependencies

        This method returns a dictionary where the keys are the package names
        and the values are the excuse names which depend on it.
        """
        res = {}
        for exc in self.excuses:
            for d in exc.deps:
                if d not in res: res[d] = []
                res[d].append(exc.name)
        return res

    def invalidate_excuses(self, valid, invalid):
        """Invalidate impossible excuses

        This method invalidates the impossible excuses, which depend
        on invalid excuses. The two parameters contains the list of
        `valid' and `invalid' excuses.
        """
        # build a lookup-by-name map
        exclookup = {}
        for e in self.excuses:
            exclookup[e.name] = e

        # build the reverse dependencies
        revdeps = self.reversed_exc_deps()

        # loop on the invalid excuses
        i = 0
        while i < len(invalid):
            # if there is no reverse dependency, skip the item
            if invalid[i] not in revdeps:
                i += 1
                continue
            # if the dependency can be satisfied by a testing-proposed-updates excuse, skip the item
            if (invalid[i] + "_tpu") in valid:
                i += 1
                continue
            # loop on the reverse dependencies
            for x in revdeps[invalid[i]]:
                # if the item is valid and it is marked as `dontinvalidate', skip the item
                if x in valid and exclookup[x].dontinvalidate:
                    continue

                # otherwise, invalidate the dependency and mark as invalidated and
                # remove the depending excuses
                exclookup[x].invalidate_dep(invalid[i])
                if x in valid:
                    p = valid.index(x)
                    invalid.append(valid.pop(p))
                    exclookup[x].addhtml("Invalidated by dependency")
                    exclookup[x].addhtml("Not considered")
            i = i + 1
 
    def write_excuses(self):
        """Produce and write the update excuses

        This method handles the update excuses generation: the packages are
        looked at to determine whether they are valid candidates. For the details
        of this procedure, please refer to the module docstring.
        """

        self.__log("Update Excuses generation started", type="I")

        # list of local methods and variables (for better performance)
        sources = self.sources
        architectures = self.options.architectures
        should_remove_source = self.should_remove_source
        should_upgrade_srcarch = self.should_upgrade_srcarch
        should_upgrade_src = self.should_upgrade_src

        # this list will contain the packages which are valid candidates;
        # if a package is going to be removed, it will have a "-" prefix
        upgrade_me = []

        # for every source package in testing, check if it should be removed
        for pkg in sources['testing']:
            if should_remove_source(pkg):
                upgrade_me.append("-" + pkg)

        # for every source package in unstable check if it should be upgraded
        for pkg in sources['unstable']:
            if sources['unstable'][pkg][FAKESRC]: continue
            # if the source package is already present in testing,
            # check if it should be upgraded for every binary package
            if pkg in sources['testing'] and not sources['testing'][pkg][FAKESRC]:
                for arch in architectures:
                    if should_upgrade_srcarch(pkg, arch, 'unstable'):
                        upgrade_me.append("%s/%s" % (pkg, arch))

            # check if the source package should be upgraded
            if should_upgrade_src(pkg, 'unstable'):
                upgrade_me.append(pkg)

        # for every source package in testing-proposed-updates, check if it should be upgraded
        for pkg in sources['tpu']:
            # if the source package is already present in testing,
            # check if it should be upgraded for every binary package
            if pkg in sources['testing']:
                for arch in architectures:
                    if should_upgrade_srcarch(pkg, arch, 'tpu'):
                        upgrade_me.append("%s/%s_tpu" % (pkg, arch))

            # check if the source package should be upgraded
            if should_upgrade_src(pkg, 'tpu'):
                upgrade_me.append("%s_tpu" % pkg)

        # process the `remove' hints, if the given package is not yet in upgrade_me
        for src in self.hints["remove"].keys():
            if src in upgrade_me: continue
            if ("-"+src) in upgrade_me: continue
            if src not in sources['testing']: continue

            # check if the version specified in the hint is the same as the considered package
            tsrcv = sources['testing'][src][VERSION]
            if not self.same_source(tsrcv, self.hints["remove"][src][0]): continue

            # add the removal of the package to upgrade_me and build a new excuse
            upgrade_me.append("-%s" % (src))
            excuse = Excuse("-%s" % (src))
            excuse.set_vers(tsrcv, None)
            excuse.addhtml("Removal request by %s" % (self.hints["remove"][src][1]))
            excuse.addhtml("Package is broken, will try to remove")
            self.excuses.append(excuse)

        # sort the excuses by daysold and name
        self.excuses.sort(lambda x, y: cmp(x.daysold, y.daysold) or cmp(x.name, y.name))

        # extract the not considered packages, which are in the excuses but not in upgrade_me
        unconsidered = [e.name for e in self.excuses if e.name not in upgrade_me]

        # invalidate impossible excuses
        for e in self.excuses:
            for d in e.deps:
                if d not in upgrade_me and d not in unconsidered:
                    e.addhtml("Unpossible dep: %s -> %s" % (e.name, d))
        self.invalidate_excuses(upgrade_me, unconsidered)

        # sort the list of candidates
        self.upgrade_me = sorted(upgrade_me)

        # write excuses to the output file
        if not self.options.dry_run:
            self.__log("> Writing Excuses to %s" % self.options.excuses_output, type="I")
            f = open(self.options.excuses_output, 'w')
            f.write("<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.01//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n")
            f.write("<html><head><title>excuses...</title>")
            f.write("<meta http-equiv=\"Content-Type\" content=\"text/html;charset=utf-8\"></head><body>\n")
            f.write("<p>Generated: " + time.strftime("%Y.%m.%d %H:%M:%S %z", time.gmtime(time.time())) + "</p>\n")
            f.write("<ul>\n")
            for e in self.excuses:
                f.write("<li>%s" % e.html())
            f.write("</ul></body></html>\n")
            f.close()

        self.__log("Update Excuses generation completed", type="I")

    # Upgrade run
    # -----------

    def newlyuninst(self, nuold, nunew):
        """Return a nuninst statstic with only new uninstallable packages

        This method subtracts the uninstallable packages of the statistic
        `nunew` from the statistic `nuold`.

        It returns a dictionary with the architectures as keys and the list
        of uninstallable packages as values.
        """
        res = {}
        for arch in nuold:
            if arch not in nunew: continue
            res[arch] = [x for x in nunew[arch] if x not in nuold[arch]]
        return res

    def get_nuninst(self, requested_arch=None, build=False):
        """Return the uninstallability statistic for all the architectures

        To calculate the uninstallability counters, the method checks the
        installability of all the packages for all the architectures, and
        tracks dependencies in a recursive way. The architecture
        independent packages are checked only for the `nobreakall`
        architectures.

        It returns a dictionary with the architectures as keys and the list
        of uninstallable packages as values.
        """
        # if we are not asked to build the nuninst, read it from the cache
        if not build:
            return self.read_nuninst()

        nuninst = {}

        # local copies for better performance
        binaries = self.binaries['testing']
        systems = self.systems

        # for all the architectures
        for arch in self.options.architectures:
            if requested_arch and arch != requested_arch: continue
            # if it is in the nobreakall ones, check arch-independent packages too
            if arch not in self.options.nobreakall_arches.split():
                skip_archall = True
            else: skip_archall = False

            # check all the packages for this architecture, calling add_nuninst if a new
            # uninstallable package is found
            nuninst[arch] = set()
            for pkg_name in binaries[arch][0]:
                r = systems[arch].is_installable(pkg_name)
                if not r:
                    nuninst[arch].add(pkg_name)

            # if they are not required, remove architecture-independent packages
            nuninst[arch + "+all"] = nuninst[arch].copy()
            if skip_archall:
                for pkg in nuninst[arch + "+all"]:
                    bpkg = binaries[arch][0][pkg]
                    if bpkg[ARCHITECTURE] == 'all':
                        nuninst[arch].remove(pkg)

        # return the dictionary with the results
        return nuninst

    def eval_nuninst(self, nuninst, original=None):
        """Return a string which represents the uninstallability counters

        This method returns a string which represents the uninstallability
        counters reading the uninstallability statistics `nuninst` and, if
        present, merging the results with the `original` one.

        An example of the output string is:
        1+2: i-0:a-0:a-0:h-0:i-1:m-0:m-0:p-0:a-0:m-0:s-2:s-0

        where the first part is the number of broken packages in non-break
        architectures + the total number of broken packages for all the
        architectures.
        """
        res = []
        total = 0
        totalbreak = 0
        for arch in self.options.architectures:
            if arch in nuninst:
                n = len(nuninst[arch])
            elif original and arch in original:
                n = len(original[arch])
            else: continue
            if arch in self.options.break_arches.split():
                totalbreak = totalbreak + n
            else:
                total = total + n
            res.append("%s-%d" % (arch[0], n))
        return "%d+%d: %s" % (total, totalbreak, ":".join(res))

    def eval_uninst(self, nuninst):
        """Return a string which represents the uninstallable packages

        This method returns a string which represents the uninstallable
        packages reading the uninstallability statistics `nuninst`.

        An example of the output string is:
            * i386: broken-pkg1, broken-pkg2
        """
        parts = []
        for arch in self.options.architectures:
            if arch in nuninst and len(nuninst[arch]) > 0:
                parts.append("    * %s: %s\n" % (arch,", ".join(sorted(nuninst[arch]))))
        return "".join(parts)

    def is_nuninst_asgood_generous(self, old, new):
        diff = 0
        for arch in self.options.architectures:
            if arch in self.options.break_arches.split(): continue
            diff = diff + (len(new[arch]) - len(old[arch]))
        return diff <= 0

    def check_installable(self, pkg, arch, suite, excluded=[], conflicts=False):
        """Check if a package is installable

        This method analyzes the dependencies of the binary package specified
        by the parameter `pkg' for the architecture `arch' within the suite
        `suite'. If the dependency can be satisfied in the given `suite` and
        `conflicts` parameter is True, then the co-installability with 
        conflicts handling is checked.

        The dependency fields checked are Pre-Depends and Depends.

        The method returns a boolean which is True if the given package is
        installable.

        NOTE: this method has been deprecated, actually we use is_installable
        from the britney c extension called within a testing system. See
        self.build_systems for more information.
        """
        self.__log("WARNING: method check_installable is deprecated: use is_installable instead!", type="E")

        # retrieve the binary package from the specified suite and arch
        binary_u = self.binaries[suite][arch][0][pkg]

        # local copies for better performances
        parse_depends = apt_pkg.ParseDepends
        get_dependency_solvers = self.get_dependency_solvers

        # analyze the dependency fields (if present)
        for type in (PREDEPENDS, DEPENDS):
            if not binary_u[type]:
                continue

            # for every block of dependency (which is formed as conjunction of disconjunction)
            for block in parse_depends(binary_u[type]):
                # if the block is not satisfied, return False
                solved, packages = get_dependency_solvers(block, arch, 'testing', excluded, strict=True)
                if not solved:
                    return False

        # otherwise, the package is installable (not considering conflicts)
        # if the conflicts handling is enabled, then check conflicts before
        # saying that the package is really installable
        if conflicts:
            return self.check_conflicts(pkg, arch, excluded, {}, {})

        return True

    def check_conflicts(self, pkg, arch, broken, system, conflicts):
        """Check if a package can be installed satisfying the conflicts

        This method checks if the `pkg` package from the `arch` architecture
        can be installed (excluding `broken` packages) within the system
        `system` along with all its dependencies. This means that all the
        conflicts relationships are checked in order to achieve the test
        co-installability of the package.

        The method returns a boolean which is True if the given package is
        co-installable in the given system.
        """

        # local copies for better performances
        binaries = self.binaries['testing'][arch]
        parse_depends = apt_pkg.ParseDepends
        check_depends = apt_pkg.CheckDep

        # unregister conflicts, local method to remove conflicts
        # registered from a given package.
        def unregister_conflicts(pkg, conflicts):
            for c in conflicts.keys():
                i = 0
                while i < len(conflicts[c]):
                    if conflicts[c][i][3] == pkg:
                        del conflicts[c][i]
                    else: i = i + 1
                if len(conflicts[c]) == 0:
                    del conflicts[c]

        def remove_package(pkg, system, conflicts):
            for k in system:
                if pkg in system[k][1]:
                    system[k][1].remove(pkg)
            unregister_conflicts(pkg, conflicts)

        # handle a conflict, local method to solve a conflict which happened
        # in the system; the behaviour of the conflict-solver is:
        #   1. If there are alternatives for the package which must be removed,
        #      try them, and if one of them resolves the system return True;
        #   2. If none of the alternatives can solve the conflict, then call
        #      itself for the package which depends on the conflicting package.
        #   3. If the top of the dependency tree is reached, then the conflict
        #      can't be solved, so return False.
        def handle_conflict(pkg, source, system, conflicts):
            # skip packages which don't have reverse dependencies
            if source not in system or system[source][1] == []:
                remove_package(source, system, conflicts)
                return (system, conflicts)
            # reached the top of the tree
            if not system[source][1][0]:
                return False
            # remove its conflicts
            unregister_conflicts(source, conflicts)
            # if there are alternatives, try them
            alternatives = system[source][0]
            for alt in alternatives:
                if satisfy(alt, [x for x in alternatives if x != alt], pkg_from=system[source][1],
                        system=system, conflicts=conflicts, excluded=[source]):
                    remove_package(source, system, conflicts)
                    return (system, conflicts)
            # there are no good alternatives, so remove the package which depends on it
            for p in system[source][1]:
                # the package does not exist, we reached the top of the tree
                if not p: return False
                # we are providing the package we conflict on (eg. exim4 and mail-transfer-agent), skip it
                if p == pkg: continue
                output = handle_conflict(pkg, p, system, conflicts)
                if output:
                    system, conflicts = output
                else: return False
            remove_package(source, system, conflicts)
            return (system, conflicts)

        # dependency tree satisfier, local method which tries to satisfy the dependency
        # tree for a given package. It calls itself recursively in order to check the
        # co-installability of the full tree of dependency of the starting package.
        # If a conflict is detected, it tries to handle it calling the handle_conflict
        # method; if it can't be resolved, then it returns False.
        def satisfy(pkg, pkg_alt=None, pkg_from=None, system=system, conflicts=conflicts, excluded=[]):
            # if it is a real package and it is already installed, skip it and return True
            if pkg in binaries[0]:
                if pkg in system:
                    if type(pkg_from) == list:
                        system[pkg][1].extend(pkg_from)
                    else:
                        system[pkg][1].append(pkg_from)
                    system[pkg] = (system[pkg][1], filter(lambda x: x in pkg_alt, system[pkg][0]))
                    return True
                binary_u = binaries[0][pkg]
            else: binary_u = None

            # if it is a virtual package
            providers = []
            if pkg_from and pkg in binaries[1]:
                providers = binaries[1][pkg]
                # it is both real and virtual, so the providers are alternatives
                if binary_u:
                    providers = filter(lambda x: (not pkg_alt or x not in pkg_alt) and x != pkg, providers)
                    if not pkg_alt:
                        pkg_alt = []
                    pkg_alt.extend(providers)
                # try all the alternatives and if none of them suits, give up and return False
                else:
                    # if we already have a provider in the system, everything is ok and return True
                    if len(filter(lambda x: x in providers and x not in excluded, system)) > 0:
                        return True
                    for p in providers:
                        # try to install the providers skipping excluded packages,
                        # which we already tried but do not work
                        if p in excluded: continue
                        elif satisfy(p, [a for a in providers if a != p], pkg_from):
                            return True
                    # if none of them suits, return False
                    return False

            # if the package doesn't exist, return False
            if not binary_u: return False

            # it is broken, but we have providers
            if pkg in broken and pkg_from:
                for p in providers:
                    # try to install the providers skipping excluded packages,
                    # which we already tried but do not work
                    if p in excluded: continue
                    elif satisfy(p, [a for a in providers if a != p], pkg_from):
                        return True
                return False

            # install the package into the system, recording which package required it
            if type(pkg_from) != list:
                pkg_from = [pkg_from]
            system[pkg] = (pkg_alt or [], pkg_from)

            # register provided packages
            if binary_u[PROVIDES]:
                for p in binary_u[PROVIDES]:
                    if p in system:
                        # do not consider packages providing the one which we are checking
                        if len(system[p][1]) == 1 and system[p][1][0] == None: continue
                        system[p][1].append(pkg)
                    else:
                        system[p] = ([], [pkg])

            # check the conflicts
            if pkg in conflicts:
                for name, version, op, conflicting in conflicts[pkg]:
                    if conflicting in binary_u[PROVIDES] and system[conflicting][1] == [pkg]: continue
                    if op == '' and version == '' or check_depends(binary_u[VERSION], op, version):
                        # if conflict is found, check if it can be solved removing
                        # already-installed packages without breaking the system; if
                        # this is not possible, give up and return False
                        output = handle_conflict(pkg, conflicting, system.copy(), conflicts.copy())
                        if output:
                            system, conflicts = output
                        else:
                            del system[pkg]
                            return False

            # register conflicts from the just-installed package
            if binary_u[CONFLICTS]:
                for block in map(operator.itemgetter(0), parse_depends(binary_u[CONFLICTS] or [])):
                    name, version, op = block
                    # skip conflicts for packages provided by itself
                    # if the conflicting package is in the system (and it is not a self-conflict)
                    if not (name in binary_u[PROVIDES] and system[name][1] == [pkg]) and \
                       block[0] != pkg and block[0] in system:
                        if block[0] in binaries[0]:
                            binary_c = binaries[0][block[0]]
                        else: binary_c = None
                        if op == '' and version == '' or binary_c and check_depends(binary_c[VERSION], op, version):
                            # if conflict is found, check if it can be solved removing
                            # already-installed packages without breaking the system; if
                            # this is not possible, give up and return False
                            output = handle_conflict(pkg, name, system.copy(), conflicts.copy())
                            if output:
                                system, conflicts = output
                            else:
                                del system[pkg]
                                unregister_conflicts(pkg, conflicts)
                                return False
                    # register the conflict
                    if block[0] not in conflicts:
                        conflicts[block[0]] = []
                    conflicts[block[0]].append((name, version, op, pkg))

            # list all its dependencies ...
            dependencies = []
            for key in (PREDEPENDS, DEPENDS):
                if not binary_u[key]: continue
                dependencies.extend(parse_depends(binary_u[key]))

            # ... and go through them
            for block in dependencies:
                # list the possible alternatives, in case of a conflict
                alternatives = map(operator.itemgetter(0), block)
                valid = False
                for name, version, op in block:
                    # otherwise, if it is already installed or it is installable, the block is satisfied
                    if name in system or satisfy(name, [a for a in alternatives if a != name], pkg):
                        valid = True
                        break
                # if the block can't be satisfied, the package is not installable so
                # we need to remove it, its conflicts and its provided packages and
                # return False
                if not valid:
                    del system[pkg]
                    unregister_conflicts(pkg, conflicts)
                    for p in providers:
                        if satisfy(p, [a for a in providers if a != p], pkg_from):
                            return True
                    return False

            # if all the blocks have been satisfied, the package is installable
            return True

        # check the package at the top of the tree
        return satisfy(pkg)

    def doop_source(self, pkg):
        """Apply a change to the testing distribution as requested by `pkg`

        This method applies the changes required by the action `pkg` tracking
        them so it will be possible to revert them.

        The method returns a list of the package name, the suite where the
        package comes from, the list of packages affected by the change and
        the dictionary undo which can be used to rollback the changes.
        """
        undo = {'binaries': {}, 'sources': {}, 'virtual': {}, 'nvirtual': []}

        affected = []
        arch = None

        # local copies for better performances
        sources = self.sources
        binaries = self.binaries['testing']

        # removal of single-arch binary package = "-<package>/<arch>"
        if pkg[0] == "-" and "/" in pkg:
            pkg_name, arch = pkg.split("/")
            pkg_name = pkg_name[1:]
            suite = "testing"
        # arch = "<source>/<arch>",
        elif "/" in pkg:
            pkg_name, arch = pkg.split("/")
            if arch.endswith("_tpu"):
                arch, suite = arch.split("_")
            else: suite = "unstable"
        # removal of source packages = "-<source>",
        elif pkg[0] == "-":
            pkg_name = pkg[1:]
            suite = "testing"
        # testing-proposed-updates = "<source>_tpu"
        elif pkg.endswith("_tpu"):
            pkg_name = pkg[:-4]
            suite = "tpu"
        # normal update of source packages = "<source>"
        else:
            pkg_name = pkg
            suite = "unstable"

        # remove all binary packages (if the source already exists)
        if not (arch and pkg[0] == '-'):
            if pkg_name in sources['testing']:
                source = sources['testing'][pkg_name]
                # remove all the binaries
                for p in source[BINARIES]:
                    binary, parch = p.split("/")
                    if arch and parch != arch: continue
                    # do not remove binaries which have been hijacked by other sources
                    if binaries[parch][0][binary][SOURCE] != pkg_name: continue
                    # if a smooth update is possible for the package, skip it
                    if not self.options.compatible and suite == 'unstable' and \
                       binary not in self.binaries[suite][parch][0] and \
                       ('ALL' in self.options.smooth_updates or \
                        binaries[parch][0][binary][SECTION] in self.options.smooth_updates):
                        continue
                    # save the old binary for undo
                    undo['binaries'][p] = binaries[parch][0][binary]
                    # all the reverse dependencies are affected by the change
                    affected.extend( [ (x, parch) for x in \
                                       self.get_reverse_tree(binary, parch, 'testing') ] )
                    affected = list(set(affected))
                    # remove the provided virtual packages
                    for j in binaries[parch][0][binary][PROVIDES]:
                        key = j + "/" + parch
                        if key not in undo['virtual']:
                            undo['virtual'][key] = binaries[parch][1][j][:]
                        binaries[parch][1][j].remove(binary)
                        if len(binaries[parch][1][j]) == 0:
                            del binaries[parch][1][j]
                    # finally, remove the binary package
                    del binaries[parch][0][binary]
                    self.systems[parch].remove_binary(binary)
                # remove the source package
                if not arch:
                    undo['sources'][pkg_name] = source
                    del sources['testing'][pkg_name]
            else:
                # the package didn't exist, so we mark it as to-be-removed in case of undo
                undo['sources']['-' + pkg_name] = True

        # single binary removal
        elif pkg_name in binaries[arch][0]:
            undo['binaries'][pkg_name + "/" + arch] = binaries[arch][0][pkg_name]
            affected.extend( [ (x, arch) for x in \
               self.get_reverse_tree(pkg_name, arch, 'testing') ] )
            affected = list(set(affected))
            del binaries[arch][0][pkg_name]
            self.systems[arch].remove_binary(pkg_name)

        # add the new binary packages (if we are not removing)
        if pkg[0] != "-":
            source = sources[suite][pkg_name]
            for p in source[BINARIES]:
                binary, parch = p.split("/")
                if arch and parch != arch: continue
                key = (binary, parch)
                # obviously, added/modified packages are affected
                if key not in affected: affected.append(key)
                # if the binary already exists (built from another source)
                if binary in binaries[parch][0]:
                    # save the old binary package
                    undo['binaries'][p] = binaries[parch][0][binary]
                    # all the reverse dependencies are affected by the change
                    affected.extend( [ (x, parch) for x in \
                                        self.get_reverse_tree(binary, parch, 'testing') ] )
                    affected = list(set(affected))
                    # all the reverse conflicts and their dependency tree are affected by the change
                    for j in binaries[parch][0][binary][RCONFLICTS]:
                        key = (j, parch)
                        if key not in affected: affected.append(key)
                        for p in self.get_full_tree(j, parch, 'testing'):
                            key = (p, parch)
                            if key not in affected: affected.append(key)
                    self.systems[parch].remove_binary(binary)
                # add/update the binary package
                binaries[parch][0][binary] = self.binaries[suite][parch][0][binary]
                self.systems[parch].add_binary(binary, binaries[parch][0][binary][:PROVIDES] + \
                    [", ".join(binaries[parch][0][binary][PROVIDES]) or None])
                # register new provided packages
                for j in binaries[parch][0][binary][PROVIDES]:
                    key = j + "/" + parch
                    if j not in binaries[parch][1]:
                        undo['nvirtual'].append(key)
                        binaries[parch][1][j] = []
                    elif key not in undo['virtual']:
                        undo['virtual'][key] = binaries[parch][1][j][:]
                    binaries[parch][1][j].append(binary)
                # all the reverse dependencies are affected by the change
                affected.extend( [ (x, parch) for x in \
                                    self.get_reverse_tree(binary, parch, 'testing') ] )
                affected = list(set(affected))

            # register reverse dependencies and conflicts for the new binary packages
            for p in source[BINARIES]:
                binary, parch = p.split("/")
                if arch and parch != arch: continue
                self.register_reverses(binary, binaries[parch][0] , binaries[parch][1])

            # add/update the source package
            if not arch:
                sources['testing'][pkg_name] = sources[suite][pkg_name]

        # return the package name, the suite, the list of affected packages and the undo dictionary
        return (pkg_name, suite, affected, undo)

    def get_reverse_tree(self, pkg, arch, suite):
        packages = []
        binaries = self.binaries[suite][arch][0]

        rev_deps = set(binaries[pkg][RDEPENDS])
        seen = set()
        while len(rev_deps) > 0:
            # mark all of the current iteration of packages as affected
            packages.extend( [ x for x in rev_deps ] )
            # and as processed
            seen |= rev_deps
            # generate the next iteration, which is the reverse-dependencies of
            # the current iteration
            new_rev_deps = [ binaries[x][RDEPENDS] for x in rev_deps \
                             if x in binaries ]
            # flatten the list-of-lists, filtering out already handled packages
            # in the process
            rev_deps = set([ package for sublist in new_rev_deps \
                             for package in sublist if package not in seen ])
        # remove duplicates from the list of affected packages
        packages = list(set(packages))
        return packages

    def get_full_tree(self, pkg, arch, suite):
        """Calculate the full dependency tree for the given package

        This method returns the full dependency tree for the package `pkg`,
        inside the `arch` architecture for the suite `suite`.
        """
        packages = [pkg]
        binaries = self.binaries[suite][arch][0]
        if pkg in binaries:
            l = n = 0
            while len(packages) > l:
                l = len(packages)
                for p in packages[n:]:
                    packages.extend([x for x in binaries[p][RDEPENDS] if x not in packages and x in binaries])
                n = l
            return packages
        else:
            return []

    def iter_packages(self, packages, selected, hint=False, nuninst=None):
        """Iter on the list of actions and apply them one-by-one

        This method applies the changes from `packages` to testing, checking the uninstallability
        counters for every action performed. If the action does not improve them, it is reverted.
        The method returns the new uninstallability counters and the remaining actions if the
        final result is successful, otherwise (None, None).
        """
        extra = []
        deferred = []
        skipped = []
        mark_passed = False
        position = len(packages)

        if nuninst:
            nuninst_comp = nuninst.copy()
        else:
            nuninst_comp = self.nuninst_orig.copy()

        # local copies for better performance
        binaries = self.binaries['testing']
        sources = self.sources
        systems = self.systems
        architectures = self.options.architectures
        nobreakall_arches = self.options.nobreakall_arches.split()
        new_arches = self.options.new_arches.split()
        break_arches = self.options.break_arches.split()
        dependencies = self.dependencies
        compatible = self.options.compatible

        # pre-process a hint batch
        pre_process = {}
        if selected and hint:
            for pkg in selected:
                pkg_name, suite, affected, undo = self.doop_source(pkg)
                pre_process[pkg] = (pkg_name, suite, affected, undo)

        lundo = []
        if not hint:
            self.output_write("recur: [%s] %s %d/%d\n" % ("", ",".join(selected), len(packages), len(extra)))

        # loop on the packages (or better, actions)
        while packages:
            pkg = packages.pop(0)

            # this is the marker for the first loop
            if not compatible and not mark_passed and position < 0:
                mark_passed = True
                packages.extend(deferred)
                del deferred
            else: position -= 1

            # defer packages if their dependency has been already skipped
            if not compatible and not mark_passed:
                defer = False
                for p in dependencies.get(pkg, []):
                    if p in skipped:
                        deferred.append(pkg)
                        skipped.append(pkg)
                        defer = True
                        break
                if defer: continue

            if not hint:
                self.output_write("trying: %s\n" % (pkg))

            better = True
            nuninst = {}

            # apply the changes
            if pkg in pre_process:
                pkg_name, suite, affected, undo = pre_process[pkg]
            else:
                pkg_name, suite, affected, undo = self.doop_source(pkg)
            if hint:
                lundo.append((undo, pkg, pkg_name, suite))

            # check the affected packages on all the architectures
            for arch in ("/" in pkg and (pkg.split("/")[1].split("_")[0],) or architectures):
                if arch not in nobreakall_arches:
                    skip_archall = True
                else: skip_archall = False

                nuninst[arch] = set([x for x in nuninst_comp[arch] if x in binaries[arch][0]])
                nuninst[arch + "+all"] = set([x for x in nuninst_comp[arch + "+all"] if x in binaries[arch][0]])
                broken = nuninst[arch + "+all"]
                to_check = []

                # broken packages (first round)
                for p in [x[0] for x in affected if x[1] == arch]:
                    if p not in binaries[arch][0]: continue
                    r = systems[arch].is_installable(p)
                    if not r:
                        if p not in broken:
                            to_check.append(p)
                            broken.add(p)
                        if not (skip_archall and binaries[arch][0][p][ARCHITECTURE] == 'all'):
                            if p not in nuninst[arch]:
                                nuninst[arch].add(p)
                    else:
                        if p in broken:
                            to_check.append(p)
                            broken.remove(p)
                        if not (skip_archall and binaries[arch][0][p][ARCHITECTURE] == 'all'):
                            # if the package was previously arch:all and uninstallable
                            # and has moved to being architecture-dependent, becoming
                            # installable in the process then it will not be in the
                            # architecture-dependent uninstallability set; therefore,
                            # don't try removing it
                            if p in nuninst[arch]:
                                nuninst[arch].remove(p)
                                 

                # broken packages (second round, reverse dependencies of the first round)
                while to_check:
                    j = to_check.pop(0)
                    if j not in binaries[arch][0]: continue
                    for p in binaries[arch][0][j][RDEPENDS]:
                        if p in broken or p not in binaries[arch][0]: continue
                        r = systems[arch].is_installable(p)
                        if not r:
                            if p not in broken:
                                broken.add(p)
                                to_check.append(p)
                            if not (skip_archall and binaries[arch][0][p][ARCHITECTURE] == 'all'):
                                if p not in nuninst[arch]:
                                    nuninst[arch].add(p)
                        else:
                            if p in broken:
                                broken.remove(p)
                                to_check.append(p)
                            if not (skip_archall and binaries[arch][0][p][ARCHITECTURE] == 'all'):
                                # if the package was previously arch:all and uninstallable
                                # and has moved to being architecture-dependent, becoming
                                # installable in the process then it will not be in the
                                # architecture-dependent uninstallability set; therefore,
                                # don't try removing it
                                if p in nuninst[arch]:
                                    nuninst[arch].remove(p)

                # if we are processing hints, go ahead
                if hint:
                    nuninst_comp[arch] = nuninst[arch]
                    nuninst_comp[arch + "+all"] = nuninst[arch + "+all"]
                    continue

                # if the uninstallability counter is worse than before, break the loop
                if (("/" in pkg and arch not in new_arches) or \
                    (arch not in break_arches)) and len(nuninst[arch]) > len(nuninst_comp[arch]):
                    better = False
                    break

            # if we are processing hints or the package is already accepted, go ahead
            if hint or pkg in selected: continue

            # check if the action improved the uninstallability counters
            if better:
                lundo.append((undo, pkg, pkg_name, suite))
                selected.append(pkg)
                packages.extend(extra)
                extra = []
                self.output_write("accepted: %s\n" % (pkg))
                self.output_write("   ori: %s\n" % (self.eval_nuninst(self.nuninst_orig)))
                self.output_write("   pre: %s\n" % (self.eval_nuninst(nuninst_comp)))
                self.output_write("   now: %s\n" % (self.eval_nuninst(nuninst, nuninst_comp)))
                if len(selected) <= 20:
                    self.output_write("   all: %s\n" % (" ".join(selected)))
                else:
                    self.output_write("  most: (%d) .. %s\n" % (len(selected), " ".join(selected[-20:])))
                for k in nuninst:
                    nuninst_comp[k] = nuninst[k]
            else:
                self.output_write("skipped: %s (%d <- %d)\n" % (pkg, len(extra), len(packages)))
                self.output_write("    got: %s\n" % (self.eval_nuninst(nuninst, "/" in pkg and nuninst_comp or None)))
                self.output_write("    * %s: %s\n" % (arch, ", ".join(sorted([b for b in nuninst[arch] if b not in nuninst_comp[arch]]))))

                extra.append(pkg)
                if not mark_passed:
                    skipped.append(pkg)

                # undo the changes (source)
                for k in undo['sources'].keys():
                    if k[0] == '-':
                        del sources['testing'][k[1:]]
                    else: sources['testing'][k] = undo['sources'][k]

                # undo the changes (new binaries)
                if pkg[0] != '-' and pkg_name in sources[suite]:
                    for p in sources[suite][pkg_name][BINARIES]:
                        binary, arch = p.split("/")
                        if '/' not in pkg or pkg.endswith("/%s" % (arch)) or pkg.endswith("/%s_tpu" % (arch)):
                            del binaries[arch][0][binary]
                            self.systems[arch].remove_binary(binary)

                # undo the changes (binaries)
                for p in undo['binaries'].keys():
                    binary, arch = p.split("/")
                    if binary[0] == "-":
                        del binaries[arch][0][binary[1:]]
                        self.systems[arch].remove_binary(binary[1:])
                    else:
                        binaries[arch][0][binary] = undo['binaries'][p]
                        self.systems[arch].remove_binary(binary)
                        self.systems[arch].add_binary(binary, binaries[arch][0][binary][:PROVIDES] + \
                            [", ".join(binaries[arch][0][binary][PROVIDES]) or None])

                # undo the changes (virtual packages)
                for p in undo['nvirtual']:
                    j, arch = p.split("/")
                    del binaries[arch][1][j]
                for p in undo['virtual']:
                    j, arch = p.split("/")
                    if j[0] == '-':
                        del binaries[arch][1][j[1:]]
                    else: binaries[arch][1][j] = undo['virtual'][p]

        # if we are processing hints, return now
        if hint:
            return (nuninst_comp, [], lundo)

        self.output_write(" finish: [%s]\n" % ",".join(selected))
        self.output_write("endloop: %s\n" % (self.eval_nuninst(self.nuninst_orig)))
        self.output_write("    now: %s\n" % (self.eval_nuninst(nuninst_comp)))
        self.output_write(self.eval_uninst(self.newlyuninst(self.nuninst_orig, nuninst_comp)))
        self.output_write("\n")

        return (nuninst_comp, extra, lundo)

    def do_all(self, maxdepth=0, init=None, actions=None):
        """Testing update runner

        This method tries to update testing checking the uninstallability
        counters before and after the actions to decide if the update was
        successful or not.
        """
        selected = []
        if actions:
            upgrade_me = actions[:]
        else:
            upgrade_me = self.upgrade_me[:]
        nuninst_start = self.nuninst_orig

        # these are special parameters for hints processing
        undo = False
        force = False
        earlyabort = False
        if maxdepth == "easy" or maxdepth < 0:
            force = maxdepth < 0
            earlyabort = True
            maxdepth = 0

        # if we have a list of initial packages, check them
        if init:
            self.output_write("leading: %s\n" % (",".join(init)))
            for x in init:
                if x not in upgrade_me:
                    self.output_write("failed: %s\n" % (x))
                    return None
                selected.append(x)
                upgrade_me.remove(x)
        
        self.output_write("start: %s\n" % self.eval_nuninst(nuninst_start))
        if not force:
            self.output_write("orig: %s\n" % self.eval_nuninst(nuninst_start))

        if earlyabort:
            extra = upgrade_me[:]
            (nuninst_end, extra, lundo) = self.iter_packages(init, selected, hint=True)
            undo = True
            if force:
                self.output_write("orig: %s\n" % self.eval_nuninst(nuninst_end))
            self.output_write("easy: %s\n" % (self.eval_nuninst(nuninst_end)))
            if not force:
                self.output_write(self.eval_uninst(self.newlyuninst(nuninst_start, nuninst_end)) + "\n")
            if not force and not self.is_nuninst_asgood_generous(self.nuninst_orig, nuninst_end):
                nuninst_end, extra = None, None
        else:
            lundo = []
            if init:
                (nuninst_end, extra, tundo) = self.iter_packages(init, selected, hint=True)
                lundo.extend(tundo)
                undo = True
            else: nuninst_end = None
            (nuninst_end, extra, tundo) = self.iter_packages(upgrade_me, selected, nuninst=nuninst_end)
            lundo.extend(tundo)
            if not self.is_nuninst_asgood_generous(self.nuninst_orig, nuninst_end):
                nuninst_end, extra = None, None

        if nuninst_end:
            if not force and not earlyabort:
                self.output_write("Apparently successful\n")
            self.output_write("final: %s\n" % ",".join(sorted(selected)))
            self.output_write("start: %s\n" % self.eval_nuninst(nuninst_start))
            if not force:
                self.output_write(" orig: %s\n" % self.eval_nuninst(self.nuninst_orig))
            else:
                self.output_write(" orig: %s\n" % self.eval_nuninst(nuninst_end))
            self.output_write("  end: %s\n" % self.eval_nuninst(nuninst_end))
            if force:
                self.output_write("force breaks:\n")
                self.output_write(self.eval_uninst(self.newlyuninst(nuninst_start, nuninst_end)) + "\n")
            self.output_write("SUCCESS (%d/%d)\n" % (len(actions or self.upgrade_me), len(extra)))
            self.nuninst_orig = nuninst_end
            if not actions:
                if not earlyabort:
                    self.upgrade_me = sorted(extra)
                else:
                    self.upgrade_me = [x for x in self.upgrade_me if x not in selected]
                if not self.options.compatible:
                    self.sort_actions()
        else:
            self.output_write("FAILED\n")
            if not undo: return

            # undo all the changes
            for (undo, pkg, pkg_name, suite) in lundo:
                # undo the changes (source)
                for k in undo['sources'].keys():
                    if k[0] == '-':
                        del self.sources['testing'][k[1:]]
                    else: self.sources['testing'][k] = undo['sources'][k]

            for (undo, pkg, pkg_name, suite) in lundo:
                # undo the changes (new binaries)
                if pkg[0] != '-' and pkg_name in self.sources[suite]:
                    for p in self.sources[suite][pkg_name][BINARIES]:
                        binary, arch = p.split("/")
                        if '/' not in pkg or pkg.endswith("/%s" % (arch)) or pkg.endswith("/%s_tpu" % (arch)):
                            del self.binaries['testing'][arch][0][binary]
                            self.systems[arch].remove_binary(binary)

            for (undo, pkg, pkg_name, suite) in lundo:
                # undo the changes (binaries)
                for p in undo['binaries'].keys():
                    binary, arch = p.split("/")
                    if binary[0] == "-":
                        del self.binaries['testing'][arch][0][binary[1:]]
                        self.systems[arch].remove_binary(binary[1:])
                    else:
                        binaries = self.binaries['testing'][arch][0]
                        binaries[binary] = undo['binaries'][p]
                        self.systems[arch].remove_binary(binary)
                        self.systems[arch].add_binary(binary, binaries[binary][:PROVIDES] + \
                            [", ".join(binaries[binary][PROVIDES]) or None])

            for (undo, pkg, pkg_name, suite) in lundo:
                # undo the changes (virtual packages)
                for p in undo['nvirtual']:
                    j, arch = p.split("/")
                    del self.binaries['testing'][arch][1][j]
                for p in undo['virtual']:
                    j, arch = p.split("/")
                    if j[0] == '-':
                        del self.binaries['testing'][arch][1][j[1:]]
                    else: self.binaries['testing'][arch][1][j] = undo['virtual'][p]

    def upgrade_testing(self):
        """Upgrade testing using the unstable packages

        This method tries to upgrade testing using the packages from unstable.
        Before running the do_all method, it tries the easy and force-hint
        commands.
        """

        self.__log("Starting the upgrade test", type="I")
        self.output_write("Generated on: %s\n" % (time.strftime("%Y.%m.%d %H:%M:%S %z", time.gmtime(time.time()))))
        self.output_write("Arch order is: %s\n" % ", ".join(self.options.architectures))

        self.__log("> Calculating current uninstallability counters", type="I")
        self.nuninst_orig = self.get_nuninst()

        if not self.options.actions:
            # process `easy' hints
            for x in self.hints['easy']:
                self.do_hint("easy", x[0], x[1])

            # process `force-hint' hints
            for x in self.hints["force-hint"]:
                self.do_hint("force-hint", x[0], x[1])

        # run the first round of the upgrade
        self.__log("> First loop on the packages with depth = 0", type="I")

        # separate runs for break arches
        allpackages = []
        normpackages = self.upgrade_me[:]
        archpackages = {}
        for a in self.options.break_arches.split():
            archpackages[a] = [p for p in normpackages if p.endswith("/" + a) or p.endswith("/" + a + "_tpu")]
            normpackages = [p for p in normpackages if p not in archpackages[a]]
        self.upgrade_me = normpackages
        self.output_write("info: main run\n")
        self.do_all()
        allpackages += self.upgrade_me
        for a in self.options.break_arches.split():
            backup = self.options.break_arches
            self.options.break_arches = " ".join([x for x in self.options.break_arches.split() if x != a])
            self.upgrade_me = archpackages[a]
            self.output_write("info: broken arch run for %s\n" % (a))
            self.do_all()
            allpackages += self.upgrade_me
            self.options.break_arches = backup
        self.upgrade_me = allpackages

        if self.options.actions:
            return

        # process `hint' hints
        hintcnt = 0
        for x in self.hints["hint"][:50]:
            if hintcnt > 50:
                self.output_write("Skipping remaining hints...")
                break
            if self.do_hint("hint", x[0], x[1]):
                hintcnt += 1

        # run the auto hinter
        if not self.options.compatible or self.options.autohinter:
            self.auto_hinter()

        # smooth updates
        if not self.options.compatible and len(self.options.smooth_updates) > 0:
            self.__log("> Removing old packages left in testing from smooth updates", type="I")
            removals = self.old_libraries()
            if len(removals) > 0:
                self.output_write("Removing packages left in testing for smooth updates (%d):\n%s" % \
                    (len(removals), self.old_libraries_format(removals)))
                self.do_all(actions=removals)
                removals = self.old_libraries()
        else:
            removals = ()

        if not self.options.compatible:
            self.output_write("List of old libraries in testing (%d):\n%s" % \
                (len(removals), self.old_libraries_format(removals)))

        # output files
        if not self.options.dry_run:
            # re-write control files
            if self.options.control_files:
                self.write_controlfiles(self.options.testing, 'testing')

            # write bugs and dates
            # XXX: disabled, we don't have write permission over there
            # self.write_dates(self.options.testing, self.dates)

            # write HeidiResult
            self.write_heidi(self.options.heidi_output)

        self.__log("Test completed!", type="I")

    def hint_tester(self):
        """Run a command line interface to test hints

        This method provides a command line interface for the release team to
        try hints and evaulate the results.
        """
        self.__log("> Calculating current uninstallability counters", type="I")
        self.nuninst_orig = self.get_nuninst()

        import readline
        histfile = os.path.expanduser('~/.britney2_history')
        if os.path.exists(histfile):
            readline.read_history_file(histfile)

        while True:
            # read the command from the command line
            try:
                input = raw_input('britney> ').lower().split()
            except EOFError:
                print ""
                break
            except KeyboardInterrupt:
                print ""
                continue
            # quit the hint tester
            if input and input[0] in ('quit', 'exit'):
                break
            # run a hint
            elif input and input[0] in ('easy', 'hint', 'force-hint'):
                try:
                    self.do_hint(input[0], 'hint-tester',
                        [k.rsplit("/", 1) for k in input[1:] if "/" in k])
                except KeyboardInterrupt:
                    continue

        readline.write_history_file(histfile)

    def do_hint(self, type, who, pkgvers):
        """Process hints

        This method process `easy`, `hint` and `force-hint` hints. If the
        requested version is not in unstable, then the hint is skipped.
        """
        hintinfo = {"easy": "easy",
                    "hint": 0,
                    "force-hint": -1,}

        self.__log("> Processing '%s' hint from %s" % (type, who), type="I")
        self.output_write("Trying %s from %s: %s\n" % (type, who, " ".join( ["%s/%s" % (p,v) for (p,v) in pkgvers])))

        ok = True
        # loop on the requested packages and versions
        for pkg, v in pkgvers:
            # remove architecture
            if "/" in pkg:
                pkg = pkg[:pkg.find("/")]

            # skip removal requests
            if pkg[0] == "-":
                continue
            # handle testing-proposed-updates
            elif pkg.endswith("_tpu"):
                pkg = pkg[:-4]
                if pkg not in self.sources['tpu']: continue
                if apt_pkg.VersionCompare(self.sources['tpu'][pkg][VERSION], v) != 0:
                    self.output_write(" Version mismatch, %s %s != %s\n" % (pkg, v, self.sources['tpu'][pkg][VERSION]))
                    ok = False
            # does the package exist in unstable?
            elif pkg not in self.sources['unstable']:
                self.output_write(" Source %s has no version in unstable\n" % pkg)
                ok = False
            elif apt_pkg.VersionCompare(self.sources['unstable'][pkg][VERSION], v) != 0:
                self.output_write(" Version mismatch, %s %s != %s\n" % (pkg, v, self.sources['unstable'][pkg][VERSION]))
                ok = False
        if not ok:
            self.output_write("Not using hint\n")
            return False

        self.do_all(hintinfo[type], map(operator.itemgetter(0), pkgvers))
        return True

    def sort_actions(self):
        """Sort actions in a smart way

        This method sorts the list of actions in a smart way. In detail, it uses
        as the base sort the number of days the excuse is old, then reorders packages
        so the ones with most reverse dependencies are at the end of the loop.
        If an action depends on another one, it is put after it.
        """
        upgrade_me = [x.name for x in self.excuses if x.name in self.upgrade_me]
        for e in self.excuses:
            if e.name not in upgrade_me: continue
            # try removes at the end of the loop
            elif e.name[0] == '-':
                upgrade_me.remove(e.name)
                upgrade_me.append(e.name)
            # otherwise, put it in a good position checking its dependencies
            else:
                pos = []
                udeps = [upgrade_me.index(x) for x in e.deps if x in upgrade_me and x != e.name]
                if len(udeps) > 0:
                    pos.append(max(udeps))
                sdeps = [upgrade_me.index(x) for x in e.sane_deps if x in upgrade_me and x != e.name]
                if len(sdeps) > 0:
                    pos.append(min(sdeps))
                if len(pos) == 0: continue
                upgrade_me.remove(e.name)
                upgrade_me.insert(max(pos)+1, e.name)
                self.dependencies[e.name] = e.deps

        # replace the list of actions with the new one
        self.upgrade_me = upgrade_me

    def auto_hinter(self):
        """Auto hint circular dependencies

        This method tries to auto hint circular dependencies analyzing the update
        excuses relationships. If they build a circular dependency, which we already
        know as not-working with the standard do_all algorithm, try to `easy` them.
        """
        self.__log("> Processing hints from the auto hinter", type="I")

        # consider only excuses which are valid candidates
        excuses = dict([(x.name, x) for x in self.excuses if x.name in self.upgrade_me])

        def find_related(e, hint, first=False):
            if e not in excuses:
                return False
            excuse = excuses[e]
            if e in self.sources['testing'] and self.sources['testing'][e][VERSION] == excuse.ver[1]:
                return True
            if not first:
                hint[e] = excuse.ver[1]
            if len(excuse.deps) == 0:
                return hint
            for p in excuse.deps:
                if p in hint: continue
                if not find_related(p, hint):
                    return False
            return hint

        # loop on them
        cache = []
        for e in excuses:
            excuse = excuses[e]
            if e in self.sources['testing'] and self.sources['testing'][e][VERSION] == excuse.ver[1] or \
               len(excuse.deps) == 0:
                continue
            hint = find_related(e, {}, True)
            if hint and e in hint and hint not in cache:
                self.do_hint("easy", "autohinter", hint.items())
                cache.append(hint)

    def old_libraries(self):
        """Detect old libraries left in testing for smooth transitions

        This method detects old libraries which are in testing but no longer
        built from the source package: they are still there because other
        packages still depend on them, but they should be removed as soon
        as possible.
        """
        sources = self.sources['testing']
        testing = self.binaries['testing']
        unstable = self.binaries['unstable']
        removals = []
        for arch in self.options.architectures:
            for pkg_name in testing[arch][0]:
                pkg = testing[arch][0][pkg_name]
                if pkg_name not in unstable[arch][0] and \
                   not self.same_source(sources[pkg[SOURCE]][VERSION], pkg[SOURCEVER]):
                    removals.append("-" + pkg_name + "/" + arch)
        return removals

    def old_libraries_format(self, libs):
        """Format old libraries in a smart table"""
        libraries = {}
        for i in libs:
            pkg, arch = i.split("/")
            pkg = pkg[1:]
            if pkg in libraries:
                    libraries[pkg].append(arch)
            else:
                    libraries[pkg] = [arch]
        return "\n".join(["  " + k + ": " + " ".join(libraries[k]) for k in libraries]) + "\n"

    def nuninst_arch_report(self, nuninst, arch):
        """Print a report of uninstallable packages for one architecture."""
        all = {}
        for p in nuninst[arch]:
            pkg = self.binaries['testing'][arch][0][p]
            all.setdefault((pkg[SOURCE], pkg[SOURCEVER]), set()).add(p)

        print '* %s' % (arch,)

        for (src, ver), pkgs in sorted(all.items()):
            print '  %s (%s): %s' % (src, ver, ' '.join(sorted(pkgs)))

        print

    def output_write(self, msg):
        """Simple wrapper for output writing"""
        print msg,
        self.__output.write(msg)

    def main(self):
        """Main method
        
        This is the entry point for the class: it includes the list of calls
        for the member methods which will produce the output files.
        """
        # if running in --print-uninst mode, quit
        if self.options.print_uninst:
            return
        # if no actions are provided, build the excuses and sort them
        elif not self.options.actions:
            self.write_excuses()
            if not self.options.compatible:
                self.sort_actions()
        # otherwise, use the actions provided by the command line
        else:
            self.upgrade_me = self.options.actions.split()

        self.__output = open(self.options.upgrade_output, 'w')

        # run the hint tester
        if self.options.hint_tester:
            self.hint_tester()
        # run the upgrade test
        else:
            self.upgrade_testing()

        self.__output.close()

if __name__ == '__main__':
    Britney().main()
