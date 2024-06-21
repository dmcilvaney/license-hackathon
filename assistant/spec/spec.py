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

class SpecContents(assistant_funcs.OpenAIAssistantFunc):
    __specContentsName = "spec_contents"
    __specContentsDescription = "Get the contents of a .spec file."
    __specContentsParameters = {
        "spec_file": {
            "type": "string",
            "description": "The path to the .spec file.",
        },
        "force_read": {
            "type": "boolean",
            "description": "Force reading the file again, even if it was already read.",
            "default": False,
        },
    }

    def __init__(self) -> None:
        super().__init__(self.__specContentsName, self.__specContentsDescription, self.__specContentsParameters)
        self.was_read = {}

    def call(self, spec_file:str, force:bool=False) -> str:
        # Check if file exists!
        abs_path = os.path.abspath(spec_file)
        if not os.path.exists(abs_path):
            err = ValueError(f"File not found: {abs_path}")
            return f"{err}"
        return self.read_spec_file(spec_file, force)

    def read_spec_file(self, filePath: str, force:bool) -> str:
        # Only read .spec files
        if not filePath.endswith(".spec"):
            return "Invalid file type. Must be a .spec file."
        # Check if the file was already read
        if filePath in self.was_read and not force:
            err = ValueError(f"File already read: {filePath}, use force_read=True to force a re-read.")
            return f"{err}"
        self.was_read[filePath] = True
        # Read each line of the file, joining into a single string
        with open(filePath, 'r') as file:
            return file.read()
