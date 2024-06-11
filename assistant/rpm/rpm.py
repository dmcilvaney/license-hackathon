# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

# Defines rpm functions that allows the OpenAI assistant to request data about an RPM file.
# This package offers RpmFileList and RpmFileContent "functions".
# Each "function" is a class that has a name() method that returns the name of the function,
# and a obj() method that returns a dictionary suitable for passing to the OpenAI API.
#
# Each function may then be called by passing it a dictionary with the required parameters.

import os
import subprocess
import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from assistant_funcs import assistant_funcs


def rpm_query(filePath: str, args: list[str]) -> list[str]:
    cmd = ["rpm"] + args + [filePath]
    # Run the bash script and capture the output.
    output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)


    # If the output has the string '(contains no files)', then there are no files to list
    if "(contains no files)" in output:
        return []

    output = output.split("\n")
    output = [file for file in output if file]
    return output

def format_single_path(path: str, search_dir:str, depth: int, directory_set: set[str], license_set: set[str], document_set: set[str]) -> str:
    # Remove the search_dir from the path
    res = path[len(search_dir):]
    if res.startswith(os.path.sep):
        res = res[1:]
    # Split the path into components
    components = res.split(os.path.sep)
    # Truncate the path to the specified depth
    #print(f"TEST: {components}")
    did_prune = False
    if depth > 0:
        pruned_components = components[:depth]
        #print(f"TEST: {pruned_components}")
        did_prune = len(pruned_components) < len(components)
        components = pruned_components
    # Rejoin the components
    res = os.path.sep.join(components)
    # Restore the search_dir
    res = os.path.join(search_dir, res)
    # If we pruned the path, add an ellipsis
    if did_prune:
        res = os.path.join(res,"...")
    # Prefix the path with the appropriate prefix
    if path in directory_set:
        res = f"{RpmFileList.dir_prefix}{res}"
    elif path in license_set:
        res = f"{RpmFileList.license_prefix}{res}"
    elif path in document_set:
        res = f"{RpmFileList.doc_prefix}{res}"
    else:
        res = f"{RpmFileList.file_prefix}{res}"

    return res

class RpmFileList(assistant_funcs.OpenAIAssistantFunc):
    dir_prefix = "dir:"
    file_prefix = "file:"
    license_prefix = "license:"
    doc_prefix = "doc:"

    __rpmFileListName = "rpm_file_list"
    __rpmFileListDescription =  ("Get a list of files and directories in an RPM file. This is expensive to call, so minimize the scope of the search where reasonable. "
                                 f"Each entry in the list is prefixed with '{dir_prefix}:' for directories, '{license_prefix}:' for license files, '{doc_prefix}:' for "
                                 f"documentation files, or '{file_prefix}:' for all other files, as understood by `rpm -q...`.")
    __rpmFileListParameters = {
            "rpm_file": {
                "type": "string",
                "description": "REQUIRED: The path to the RPM file to get the file list for."
            },
            "search_dir": {
                "type": "string",
                "description": "OPTIONAL (default '/'): The subdirectory to search from. ie '/' might list ['/', '/usr', '/var'], while '/var' might list ['/var', '/var/log',  '/var/lib']."
            },
            "max_depth": {
                "type": "integer",
                "description": "OPTIONAL (default '0'): From the search_dir, limit the depth of the search. ie 1 would only list the immediate children of the search_dir. 0 means no limit."
            }
        }

    class CacheEntry:
        def __init__(self, all_files_and_dirs: list[str], dirs_set: set[str], licenses_set: set[str], docs_set: set[str]) -> None:
            self.all_files_and_dirs = all_files_and_dirs
            self.dirs_set = dirs_set
            self.licenses_set = licenses_set
            self.docs_set = docs_set

    # Shared rpm cache. Stores a list of files, licenses, docs, and dirs for each rpm file. Key is the rpm file path.
    rpm_cache = None

    def __init__(self) -> None:
        super().__init__(self.__rpmFileListName, self.__rpmFileListDescription, self.__rpmFileListParameters)
        if RpmFileList.rpm_cache is None:
            RpmFileList.rpm_cache = {}

    def call(self, rpm_file:str, search_dir:str="/", max_depth:int=0) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(rpm_file)
        if not os.path.exists(abs_path):
            err = ValueError(f"File not found: {abs_path}")
            return f"{err}"
        if max_depth < 0:
            err = ValueError(f"max_depth must be greater than or equal to 0")
            return f"{err}"
        return self.rpm_get_contents(rpm_file, search_dir, max_depth)

    def format_output(self, filePath: str, search_dir:str, depth:int) -> list[str]:
        directory_set = self.rpm_cache[filePath].dirs_set
        license_set = self.rpm_cache[filePath].licenses_set
        document_set = self.rpm_cache[filePath].docs_set

        all_files = self.rpm_cache[filePath].all_files_and_dirs

        # Normalize paths
        search_dir = os.path.normpath(search_dir)
        all_files = [os.path.normpath(file) for file in all_files]

        # Filter out files and directories that are not in the root directory
        if search_dir:
            all_files = [file for file in all_files if file.startswith(search_dir)]

        # Format the paths
        all_files = [format_single_path(file, search_dir, depth, directory_set, license_set, document_set) for file in all_files]

        # Remove duplicates
        all_files = list(set(all_files))

        # Sort based on everything after <type>:...
        all_files.sort(key=lambda x: x.split(":", 1)[1])

        return all_files

    def rpm_get_contents(self, filePath: str, search_dir:str, depth:int) -> list[str]:
        # Populate cache on first run
        if not filePath in RpmFileList.rpm_cache:
            print(f"Populating cache for {filePath}")
            all_files_and_dirs = rpm_query(filePath, ["-q", "--qf", "[%{FILEMODES:perms} %{FILENAMES}\n]"])
            all_dirs = [file.split(' ', 1)[1] for file in all_files_and_dirs if file[0] == "d"]
            # Strip the permissions from the files
            all_files_and_dirs = [file.split(' ', 1)[1] for file in all_files_and_dirs]
            licenses = rpm_query(filePath, ["-qL"])
            docs = rpm_query(filePath, ["-qd"])
            RpmFileList.rpm_cache[filePath] = RpmFileList.CacheEntry(all_files_and_dirs, set(all_dirs), set(licenses), set(docs))
            entry = RpmFileList.rpm_cache[filePath]
            #print(f"DEBUG: Cache entry is {entry.all_files_and_dirs}")
            #print(f"DEBUG: Cache entry is {entry.dirs_set}")
            #print(f"DEBUG: Cache entry is {entry.licenses_set}")
            #print(f"DEBUG: Cache entry is {entry.docs_set}")

        return self.format_output(filePath, search_dir, depth)

# Only run tests when this file is run directly
if __name__ == "__main__":
    rpm = RpmFileList()
    for line in rpm.rpm_get_contents("../nano-testing/rpms/nano-lang-6.0-2.cm2.x86_64.rpm", "/usr//share/", 2):
        print(line)

    for line in rpm.rpm_get_contents("../nano-testing/rpms/nano-lang-6.0-2.cm2.x86_64.rpm", "/usr//share/", 1):
        print(line)
