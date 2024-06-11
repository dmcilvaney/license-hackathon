# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

class OpenAIAssistantFunc:
    def __init__(self, fnName:str, fnDescription:str, fnParameters:dict) -> None:
        self.__fnName = fnName
        self.__fnDescription = fnDescription
        self.__fnParameters = fnParameters

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
    def __init__(self) -> None:
        self.functions = []

    def addFunction(self, func:OpenAIAssistantFunc) -> None:
        self.functions.append(func)

    def getFunctions(self) -> list[dict]:
        return [func.obj() for func in self.functions]

    def callFunction(self, fnName:str, args:dict) -> str:
        for func in self.functions:
            if func.name() == fnName:
                args = eval(args, None, None)
                print(f"Args: {args}")
                results = f"{func.call(**args)}"
                print(f"Results: {results}")
                return results
        raise ValueError(f"Function not found: {fnName}")
