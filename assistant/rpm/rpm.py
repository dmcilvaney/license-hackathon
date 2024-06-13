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
import time
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from assistant_funcs import assistant_funcs
import tempfile


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

class RpmName(assistant_funcs.OpenAIAssistantFunc):
    __rpmNameName = "rpm_name"
    __rpmNameDescription =  "Get the name of an RPM file as understood by `rpm -q...`."
    __rpmNameParameters = {
            "rpm_file": {
                "type": "string",
                "description": "REQUIRED: The path to the RPM file to get the name of."
            }
        }

    def __init__(self) -> None:
        super().__init__(self.__rpmNameName, self.__rpmNameDescription, self.__rpmNameParameters)

    def call(self, rpm_file:str) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(rpm_file)
        if not os.path.exists(abs_path):
            err = ValueError(f"File not found: {abs_path}")
            return f"{err}"
        return self.rpm_get_name(rpm_file)

    def rpm_get_name(self, filePath: str) -> str:
        name = rpm_query(filePath, ["-q", "--qf", "%{NAME}"])
        return name[0]

class RpmFileList(assistant_funcs.OpenAIAssistantFunc):
    dir_prefix = "dir:"
    file_prefix = "file:"
    license_prefix = "license:"
    doc_prefix = "doc:"

    __rpmFileListName = "rpm_file_list"
    __rpmFileListDescription =  ("Get a list of files and directories in an RPM file. The results may be filtered to reduce extraneous clutter."
                                 f"Each entry in the list is prefixed with '{dir_prefix}' for directories, '{license_prefix}' for license files, '{doc_prefix}' for "
                                 f"documentation files, or '{file_prefix}' for all other files, as understood by `rpm -q...`.")
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

class RpmDependencyInfo(assistant_funcs.OpenAIAssistantFunc):
    __rpmDependencyInfoName = "rpm_dependency_info"
    __rpmDependencyInfoDescription  =  ("Print everything a package provides and requires. Each line is prefixed with 'provides:' or 'requires:'. "
                                    "This dependency information will more accurate than trying to parse the spec file. ")
    __rpmDependencyInfoParameters = {
            "rpm_file": {
                "type": "string",
                "description": "REQUIRED: The path to the RPM file to get the requires and provides for."
            }
        }

    def __init__(self) -> None:
        super().__init__(self.__rpmDependencyInfoName, self.__rpmDependencyInfoDescription, self.__rpmDependencyInfoParameters)

    def call(self, rpm_file:str, search_dir:str="/", max_depth:int=0) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(rpm_file)
        if not os.path.exists(abs_path):
            err = ValueError(f"File not found: {abs_path}")
            return f"{err}"
        if max_depth < 0:
            err = ValueError(f"max_depth must be greater than or equal to 0")
            return f"{err}"
        return self.rpm_get_dep_info(rpm_file)

    def rpm_get_dep_info(self, filePath: str) -> list[str]:
        provides = rpm_query(filePath, ["-qp", "--provides", filePath])
        requires = rpm_query(filePath, ["-qp", "--requires", filePath])
        # sort
        provides.sort()
        requires.sort()

        # prefix
        provides = [f"provides:{p}" for p in provides]
        requires = [f"requires:{r}" for r in requires]

        return provides + requires

class RpmReadFile(assistant_funcs.OpenAIAssistantFunc):
    __rpm_read_file_name = "rpm_read_file"
    __rpm_read_file_description  =  ("Prints the content of a file inside an RPM file. If the file does not appear to be a text file an error will be returned."
                                        "The tool will refuse to read files that cannot be decoded as UTF-8.")
    __rpm_read_file_parameters = {
            "rpm_file": {
                "type": "string",
                "description": "REQUIRED: The path to the RPM file read the file from."
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
        super().__init__(self.__rpm_read_file_name, self.__rpm_read_file_description, self.__rpm_read_file_parameters)

    def call(self, rpm_file:str, file_path:str, max_lines:int=10) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(rpm_file)
        if not os.path.exists(abs_path):
            err = ValueError(f"File not found: {abs_path}")
            return f"{err}"
        if max_lines <= 0:
            err = ValueError(f"max_lines must be greater than 0")
            return f"{err}"
        return self.rpm_read_file(rpm_file, file_path, max_lines)

    def rpm_read_file(self, rpm_file:str, file_path:str, max_lines:int=10) -> str:
        # cpio archives prepend '.' to every path, ensure that is added to the file path
        if not file_path.startswith('.'):
            file_path = f".{file_path}"

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_file = os.path.join(tmp_dir, "file")
            with open(tmp_file, 'wb') as f:
                # Get the cpio
                rpm_cmd = subprocess.Popen(["rpm2cpio", rpm_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                # Extract the file
                cpio_cmd = subprocess.Popen(["cpio", "-i", "--to-stdout", file_path], stdin=rpm_cmd.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                # Write to the destination
                f.write(cpio_cmd.stdout.read())
                # Flush the pipes to ensure the return codes are correct
                rpm_cmd.communicate()
                cpio_cmd.communicate()
                if rpm_cmd.wait():
                    stderr = rpm_cmd.communicate()[1].decode('utf-8')
                    err = ValueError(f"rpm2cpio command failed with return code {rpm_cmd.returncode}, error: {stderr}")
                    return f"{err}"
                if cpio_cmd.wait():
                    stderr = cpio_cmd.communicate()[1].decode('utf-8')
                    err = ValueError(f"cpio command failed with return code {cpio_cmd.returncode}, error: {stderr}")
                    return f"{err}"

            # Try to read the file if we can
            try:
                with open(tmp_file, 'r', encoding='utf-8') as f:
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
    rpm1 = RpmFileList()
    rpm2 = RpmFileList()
    for line in rpm1.rpm_get_contents("./nano-testing/rpms/nano-6.0-2.cm2.x86_64.rpm", "/usr//share/", 4):
        print(line)

    for line in rpm2.rpm_get_contents("./nano-testing/rpms/nano-6.0-2.cm2.x86_64.rpm", "/usr//share/", 1):
        print(line)

    depInfo = RpmDependencyInfo()
    print(depInfo.rpm_get_dep_info("./nano-testing/rpms/nano-6.0-2.cm2.x86_64.rpm"))

    readFile = RpmReadFile()
    print(readFile.rpm_read_file("./nano-testing/rpms/nano-6.0-2.cm2.x86_64.rpm", "./usr/share/doc/nano-6.0/nano.html", 20))
    print(readFile.rpm_read_file("./nano-testing/rpms/nano-6.0-2.cm2.x86_64.rpm", "./usr/bin/nano", 20))
