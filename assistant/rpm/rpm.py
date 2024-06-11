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

def truncate_path(path: str, depth: int) -> str:
    if depth == 0:
        if path != "/":
            return "/..."
        else:
            return path

    depth = depth + 1

    res = ""
    parts = path.split("/")
    if len(parts) > depth:
        res =  "/".join(parts[:depth])
    else:
        res = path
    if res != path:
        res = res + "/..."
    return res

def rpm_get_contents(filePath: str, rootDir:str, depth:int) -> list[str]:
    print(f"filePath={filePath}, rootDir={rootDir}, depth={depth}")
    all_files_and_dirs = rpm_query(filePath, ["-q", "--qf", "[%{FILEMODES:perms} %{FILENAMES}\n]"])
    all_files = [file.split(' ', 1)[1] for file in all_files_and_dirs if file[0] != "d"]
    all_dirs = [file.split(' ', 1)[1] for file in all_files_and_dirs if file[0] == "d"]

    # Filter out files and directories that are not in the root directory
    if rootDir:
        all_files = [file for file in all_files if file.startswith(rootDir)]
        all_dirs = [dir for dir in all_dirs if dir.startswith(rootDir)]

    # Truncate any parts of the path that are deaper than the requested depth.
    # ie if depth is 1, then /usr/bin will be truncated to /usr.
    all_files = [truncate_path(f, depth) for f in all_files]
    all_dirs = [truncate_path(d, depth) for d in all_dirs]

    # Remove duplicates
    all_files = list(set(all_files))
    all_dirs = list(set(all_dirs))

    # Prefix each entry with 'd:' if it is a directory, and 'f:' if it is a file
    all_files = [f"f:{file}" for file in all_files]
    all_dirs = [f"d:{dir}" for dir in all_dirs]

    # Sort and return the lists, but sort by path. (ie ignore "d:" and "f:" prefixes when sorting.)
    results = all_dirs + all_files
    results.sort(key=lambda x: x[2:])
    return results

class RpmFileList(assistant_funcs.OpenAIAssistantFunc):
    __rpmFileListName = "rpm_file_list"
    __rpmFileListDescription =  ("Get a list of files and directories in an RPM file. This is expensive to call, so minimize the scope of the search where reasonable. "
                                 "Each entry in the list is prefixed with 'd:' if it is a directory, and 'f:' if it is a file.")
    __rpmFileListParameters = {
            "rpm_file": {
                "type": "string",
                "description": "REQUIRED: The path to the RPM file to get the file list for."
            },
            "root_dir": {
                "type": "string",
                "description": "OPTIONAL (default '/'): The subdirectory to search inside. ie '/' might list ['/', '/usr', '/var'], while '/var' might list ['/var', '/var/log',  '/var/lib']."
            },
            "depth": {
                "type": "integer",
                "description": "OPTIONAL (default '1'): How many levels deep to search. 0 is just the root directory, 1 is the root directory and its immediate children, etc."
            }
        }

    def __init__(self) -> None:
        super().__init__(self.__rpmFileListName, self.__rpmFileListDescription, self.__rpmFileListParameters)

    def call(self, rpm_file:str, root_dir:str="/", depth:int=1) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(rpm_file)
        if not os.path.exists(abs_path):
            raise ValueError(f"File not found: {abs_path}")
        return rpm_get_contents(rpm_file, root_dir, depth)

# Only run tests when this file is run directly
if __name__ == "__main__":
    for line in rpm_get_contents("../nano-testing/rpms/nano-lang-6.0-2.cm2.x86_64.rpm", "/", 1):
        print(line)
