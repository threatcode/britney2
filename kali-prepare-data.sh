#!/bin/bash

set -e

MIRROR="http://repo.kali.org/kali"
COMPONENTS="main contrib non-free"
ARCHES="i386 amd64 armel armhf"
REPOSITORIES="kali-rolling kali-rolling-only kali-dev"

download_sources() {
	dist="$1"
	for c in $COMPONENTS; do
		wget $MIRROR/dists/$dist/$c/source/Sources.gz \
			-O data/$dist/Sources_${c}.gz
	done
	zcat data/$dist/Sources_*.gz >data/$dist/Sources
}

download_packages() {
	dist="$1"
	arch="$2"
	for c in $COMPONENTS; do
		wget $MIRROR/dists/$dist/$c/binary-$arch/Packages.gz \
			-O data/$dist/Packages_${arch}_${c}.gz
		if [ "$c" = "main" ]; then
			# Include debian-installer too
			wget $MIRROR/dists/$dist/$c/debian-installer/binary-$arch/Packages.gz \
				-O data/$dist/Packages_${arch}_${c}_di.gz
		fi
	done
	zcat data/$dist/Packages_${arch}_*.gz \
		> data/$dist/Packages_$arch
}

for dist in $REPOSITORIES; do
	mkdir -p data/$dist
	touch data/$dist/BugsV
	download_sources $dist
	for arch in $ARCHES; do
		download_packages $dist $arch
	done
done

# Create empty files and other required directories
touch data/kali-rolling/Urgency
touch data/kali-rolling/Dates

mkdir -p data/empty
touch data/empty/BugsV
touch data/empty/Sources
touch data/empty/Packages_{amd64,i386,armel,armhf}

mkdir -p data/output
