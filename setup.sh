#!/bin/bash

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

set -x
set -e

script_dir=$(git rev-parse --show-toplevel)
rm -rf "${script_dir}/nano-testing"
rm -rf "${script_dir}/perl-testing"
mkdir -p "${script_dir}/nano-testing"
mkdir -p "${script_dir}/perl-testing"

repoquery -y -q --location 'nano*' --latest-limit 1 > "${script_dir}/nano-testing/rpm_urls.txt"
repoquery -y -q --location 'nano*' --latest-limit 1 --srpm > "${script_dir}/nano-testing/source_urls.txt"

# Get RPMS, SRPMS
while IFS= read -r url
do
    wget -P "${script_dir}/nano-testing/rpms/" "$url"
done < "${script_dir}/nano-testing/rpm_urls.txt"
while IFS= read -r url
do
    wget -P "${script_dir}/nano-testing/srpms/" "$url"
done < "${script_dir}/nano-testing/source_urls.txt"

# Prep each set of sources
build_dir=${script_dir}/nano-testing/build
while IFS= read -r url
do
    basename=$(basename "$url")
    wget -P "${script_dir}/nano-testing/srpms/" "$url"
    rpm -ihv "${script_dir}/nano-testing/srpms/${basename}" --define "_topdir ${build_dir}"
    rpmbuild -bp "${build_dir}/SPECS/"*".spec" --define "_topdir ${build_dir}"
done < "${script_dir}/nano-testing/source_urls.txt"

# Perl is a bit more complicated unfortunately...
perl_src_url=$(repoquery -y -q --location 'perl' --latest-limit 1 --srpm)
wget -P "${script_dir}/perl-testing/srpms/" "$perl_src_url"
build_dir=${script_dir}/perl-testing/build
perl_basename=$(basename "$perl_src_url")
rpm -ihv "${script_dir}/perl-testing/srpms/${perl_basename}" --define "_topdir ${build_dir}"
rpmbuild -bp "${build_dir}/SPECS/"*".spec" --define "_topdir ${build_dir}"

# Get all the expected packages by looking at the spec file
rpmspec -q "${build_dir}/SPECS/perl.spec" --builtrpms --define "_topdir ${build_dir}" --queryformat="%{nvr}\n" > "${script_dir}/perl-testing/rpm_names.txt"
while IFS= read -r rpm_name
do
    wget -P "${script_dir}/perl-testing/rpms/" "$(repoquery -y -q --location "$rpm_name" --latest-limit 1)" &
done < "${script_dir}/perl-testing/rpm_names.txt"
wait

set +x
echo ""
echo "**** DONE SETUP ****"
echo ""
