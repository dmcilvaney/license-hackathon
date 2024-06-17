# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json
import os

class OpenAIAssistantFunc:
    def __init__(self, fn_name:str, fn_description:str, fn_parameters:dict) -> None:
        self.__fnName = fn_name
        self.__fnDescription = fn_description
        self.__fnParameters = fn_parameters

    def name(self) -> str:
        return self.__fnName

    def choice(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.__fnName
            }
        }

    def obj(self) -> dict:
        if len(self.__fnParameters) == 0:
            params = {}
        else:
            params = {
                "type": "object",
                "properties":
                    self.__fnParameters
            }
        return {
            "type": "function",
            "function": {
                "name": self.__fnName,
                "description": self.__fnDescription,
                "parameters": params
            }
        }

    def call(self, args:dict) -> str:
        raise NotImplementedError("Subclasses must implement call() method.")

class APIFeedbackFunc(OpenAIAssistantFunc):
    __feedbackName = "api_feedback"
    __feedbackDescription = "Provide feedback on the provided API. Each actionable piece of feedback will result in a $500 bonus!"
    __feedbackParameters = {
        "api": {
            "type": "string",
            "description": "REQUIRED: The API to provide feedback for."
        },
        "feedback": {
            "type": "string",
            "description": "REQUIRED: The feedback to provide for the API."
        }
    }

    def __init__(self) -> None:
        super().__init__(self.__feedbackName, self.__feedbackDescription, self.__feedbackParameters)

    def call(self, api:str, feedback:str) -> str:
        print(f"API: {api}")
        print(f"\tFeedback: {feedback}")
        return f"Feedback received for {api}, thankyou!)"

class OpenAiAssistantFuncManager:
    prints = True
    def __init__(self) -> None:
        self.functions = []

    def addFunction(self, func:OpenAIAssistantFunc) -> None:
        # Don't add duplicate functions
        if func not in self.functions:
            self.functions.append(func)

    def getFunctions(self) -> list[dict]:
        return [func.obj() for func in self.functions]

    def callFunction(self, fnName:str, args:dict) -> str:
        for func in self.functions:
            if func.name() == fnName:
                if self.prints:
                    print(f"\t{fnName}\n\t\tArgs: {args}")
                try:
                    args = json.loads(args)
                    results = f"{func.call(**args)}"
                except Exception as e:
                    print(f"Error: {e}")
                    return f"Error calling tool: {e}"
                # print(f"Results: {results}")
                return results
        err = ValueError(f"Function not found: {fnName}")
        print(f"{err}")
        return f"{err}"
