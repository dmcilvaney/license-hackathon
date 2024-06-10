#!/bin/bash

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

set -x
set -e

script_dir=$(git rev-parse --show-toplevel)
rm -rf "${script_dir}/nano-testing"
mkdir -p "${script_dir}/nano-testing"

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

set +x
echo ""
echo "**** DONE SETUP ****"
echo ""
