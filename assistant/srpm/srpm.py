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

def sanitize_path(top_build_dir, path):
    top_build_dir = os.path.abspath(top_build_dir)
    path = os.path.normpath(path)

    # Ensure we don't go outside the build directory
    if ".." in path:
        raise ValueError(f"Error: search_dir cannot go outside the build directory, do not use '..' in the path.")

    final_path = os.path.join(top_build_dir, path)
    final_path = os.path.abspath(final_path)
    return final_path

class SrpmCache:
    srpm_cache = {}
    class SrpmCacheEntry:
        def __init__(self, top_build_dir) -> None:
            self.top_build_dir = top_build_dir

    def get_from_cache(self, srpm_file):
        if not srpm_file in self.srpm_cache:
            # Hack for testing, hard-code the topdir
            self.srpm_cache[srpm_file] = SrpmCache.SrpmCacheEntry("/home/damcilva/repos/license-hackathon/nano-testing/build/BUILD")
        return self.srpm_cache[srpm_file].top_build_dir

srpm_cache = SrpmCache()

class SrpmExploreFiles(assistant_funcs.OpenAIAssistantFunc):
    dir_prefix = "dir:"
    file_prefix = "file:"
    __srpm_explore_files_name = "srpm_explore_files"
    __srpm_explore_files_description =  ("Explores the files created by running `rpmbuild -bp` on an SRPM file. "
                                        "This function will return a list of files and directories. "
                                        f"Each entry in the list is prefixed with '{dir_prefix}' for directories, '{file_prefix}' for files"
                                        "Be cautious when setting max_depth beyond 1 or 2, as this may result in a large number of files being returned.")
    __srpm_explore_files_parameters = {
            "srpm_file": {
                "type": "string",
                "description": "REQUIRED: The path to the SRPM file to get the file list for."
            },
            "search_dir": {
                "type": "string",
                "description": "OPTIONAL (default '.'): The subdirectory to search from. ie './' might list ['./mypkg-v1/src', './mypkg-v1/docs', './mypkg-v1/readme.md', ...], "
                "while './mypkg-v1/src' might list ['./mypkg-v1/tool.c', './mypkg-v1/header.h', ...]. "
                "All paths are relative to the /usr/src/<dist>/BUILD directory. No paths will be allowed outside of this directory."
            },
            "max_depth": {
                "type": "integer",
                "description": "OPTIONAL (default '2'): From the search_dir, limit the depth of the search. ie 1 would only list the immediate children of the search_dir. 0 means no limit."
                "Because of the layout of rpm build directories (package sources are often inside a '<pkg>' directory), setting this to at least 2 is recommended."
            }
        }

    # Shared rpm cache. Stores a list of files, licenses, docs, and dirs for each rpm file. Key is the rpm file path.
    srpm_cache = None

    def __init__(self) -> None:
        super().__init__(self.__srpm_explore_files_name, self.__srpm_explore_files_description, self.__srpm_explore_files_parameters)
        if SrpmExploreFiles.srpm_cache is None:
            SrpmExploreFiles.srpm_cache = {}

    def call(self, srpm_file:str, search_dir:str=".", max_depth:int=1) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(srpm_file)
        if not os.path.exists(abs_path):
            err = ValueError(f"File not found: {abs_path}")
            return f"{err}"
        if max_depth < 0:
            err = ValueError(f"max_depth must be greater than or equal to 0")
            return f"{err}"
        return self.srpm_explore_contents(srpm_file, search_dir, max_depth)

    def srpm_explore_contents(self, srpm_file: str, search_dir:str, max_depth: int) -> list[str]:
        build_dir = srpm_cache.get_from_cache(srpm_file)
        #base_path_abs = sanitize_path(build_dir, ".")
        try:
            final_path = sanitize_path(build_dir, search_dir)
        except ValueError as e:
            return e

        # Get all files and dirs using 'find'
        files = []
        dirs = []
        base_depth = final_path.count(os.path.sep)
        p_debug = True
        for root, dir_list, file_list in os.walk(final_path):
            relative_depth = root.count(os.path.sep) - base_depth

            if max_depth > 0 and relative_depth >= max_depth:
                continue

            dirs.extend([os.path.join(root, dir) for dir in dir_list])
            files.extend([os.path.join(root, file) for file in file_list])

            # for file in file_list:
            #     if os.path.isfile(os.path.join(root, file)):
            #         files.append(os.path.join(root, file))
            #     else:
            #         dirs.append(os.path.join(root, file))

        # Remove the common prefix from the paths
        files = [file.removeprefix(final_path+os.path.sep) for file in files]
        dirs = [dir.removeprefix(final_path+os.path.sep) for dir in dirs]

        # Format the paths
        files = [f"{self.file_prefix}{file}" for file in files]
        dirs = [f"{self.dir_prefix}{dir}{os.path.sep}" for dir in dirs]

        # Merge and sort
        all_files = list(set(files + dirs))
        all_files.sort(key=lambda x: x.split(":", 1)[1])

        return all_files

class SrpmReadFile(assistant_funcs.OpenAIAssistantFunc):
    __srpm_read_file_name = "srpm_read_file"
    __rpmDependencyInfoDescription  =  ("Prints the content of a file inside an SRPM file after running the %prep stage. "
                                        "If the file does not appear to be a text file an error will be returned. "
                                        "The tool will refuse to read files that cannot be decoded as UTF-8.")
    __rpmDependencyInfoParameters = {
            "srpm_file": {
                "type": "string",
                "description": "REQUIRED: The path to the SRPM file read the file from."
            },
            "file_path": {
                "type": "string",
                "description": "REQUIRED: The path to the file to read."
            },
            "max_lines": {
                "type": "integer",
                "description": "OPTIONAL (default '10'): The maximum number of lines to read from the file."
            }
        }

    def __init__(self) -> None:
        super().__init__(self.__srpm_read_file_name, self.__rpmDependencyInfoDescription, self.__rpmDependencyInfoParameters)

    def call(self, srpm_file:str, file_path:str, max_lines:int=10) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(srpm_file)
        if not os.path.exists(abs_path):
            err = ValueError(f"File not found: {abs_path}")
            return f"{err}"
        if max_lines <= 0:
            err = ValueError(f"max_lines must be greater than 0")
            return f"{err}"
        return self.srpm_read_file(srpm_file, file_path, max_lines)

    def srpm_read_file(self, rpm_file:str, file_path:str, max_lines:int=10) -> str:
        build_dir = srpm_cache.get_from_cache(rpm_file)
        try:
            final_path = sanitize_path(build_dir, file_path)
        except ValueError as e:
            return e

        if not os.path.exists(final_path):
            return f"File not found: {final_path}"

         # Try to read the file if we can
        try:
            with open(final_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) > max_lines:
                    lines = lines[:max_lines]
                # Join the lines into a single string with '\n' between each line
                lines = "".join(lines)
                return lines
        except UnicodeDecodeError:
            err = ValueError(f"File '{rpm_file}' does not appear to be a text file, refusing to print.")
            return f"{err}"

# Only run tests when this file is run directly
if __name__ == "__main__":
    srpm = SrpmExploreFiles()
    for line in srpm.srpm_explore_contents("nano.src.rpm", "./nano-6.0/src", 2):
        print(line)

    srpm_reader = SrpmReadFile()
    print(srpm_reader.srpm_read_file("nano.src.rpm", "./nano-6.0/src/nano.c", 10))
