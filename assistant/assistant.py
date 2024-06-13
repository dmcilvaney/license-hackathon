#!/bin/python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import sys
import time

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

import rpm.rpm
import spec.spec
import srpm.srpm
import assistant_funcs.assistant_funcs

timeout_override = 120

class ProvideAssessmentFunc(assistant_funcs.assistant_funcs.OpenAIAssistantFunc):
    issue_list = []
    __declareIssueName = "provide_assessment"
    __declareIssueDescription = "Provide an assessment of the licensing situation for the provided packages."
    __declareIssueParameters = {
        "file": {
            "type": "string",
            "description": "REQUIRED: The file to declare an issue with."
        },
        "has_issue": {
            "type": "boolean",
            "description": "REQUIRED: Whether an issue exists with the file."
        },
        "severity": {
            "type": "string",
            "enum": ["none", "low", "medium", "high"],
            "description": "Optional: The severity of the issue, defaults to 'none'. Omit if has_issue=False"
        },
        "description": {
            "type": "string",
            "description": "Optional: A brief description of the issue. Omit if has_issue=False."
        }
    }

    def __init__(self) -> None:
        super().__init__(self.__declareIssueName, self.__declareIssueDescription, self.__declareIssueParameters)

    def call(self, file, has_issue, severity="none", description=None) -> str:
        if not file:
            return "File is required."
        if has_issue:
            if severity not in ["low", "medium", "high"]:
                return f"Invalid severity level '{severity}', must be one of 'low', 'medium', or 'high' if an issue exists."
            if not description:
                return "Description is required if an issue exists."
        else:
            if severity != "none":
                return "Only severity level 'none' is valid if no issue exists."
            if description:
                return "Description is only valid if an issue exists."
        self.issue_list.append({
            "file": file,
            "has_issue": has_issue,
            "severity": severity,
            "description": description
        })
        return f"Assessment for '{file}' added."

    def get_issues():
        return ProvideAssessmentFunc.issue_list


def create_assistant(tools):
    """Returns a new client and assistant.
    :rtype: tuple
    :return: A tuple of the client and assistant.
    """
    print(f"AZURE_OPENAI_ENDPOINT:{os.environ['AZURE_OPENAI_ENDPOINT']}")
    print(f"CHAT_COMPLETIONS_DEPLOYMENT_NAME:{os.environ['CHAT_COMPLETIONS_DEPLOYMENT_NAME']}")
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    deployment = os.environ["CHAT_COMPLETIONS_DEPLOYMENT_NAME"]

    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2024-05-01-preview",
        max_retries=20,
        timeout=timeout_override,
    )
    # https://platform.openai.com/docs/api-reference/assistants/createAssistant
    license_assistant = client.beta.assistants.create(
        name="License Assistant",
        instructions=f"You are a very skilled AI assistant that specializes in working with open source project licenses. "
        f"You have access to a sandbox environment where you can investigate a .rpm file, the .src.rpm it was generated from, and the .spec file used to generate it. "
        f"Your goal is to determine if all .rpm files have suitable license files included in them, and if the license files are correct. "
        f"You may access the contents of the .rpm files, the .src.rpm file, and the .spec file via the provided functions. "
        "Extra Background: Not every .rpm must have license files:\n"
        "- a package with executables will likely require a license file, check the source RPM to determine this\n"
        "- a package with other types of files may not require a license\n"
        "- a package may use a 'Requires' directive to pull in a license file from another sub-package in the same .spec file\n"
        "- etc.\n"
        " (e.g. a -devel package may require the license file from the main package, or a main package may use the license files from a -libs subpackage) "
        "Consider the interdependencies between packages when determining if a license file is required. Any such dependencies must be explicitly stated in the .spec file, or "
        "validated via querying the .rpm files' dependencies. Documentation is insufficient to ensure license compliance. "
        "The .spec file should be considered unreliable, as it may not accurately reflect the actual licensing requirements of the package. Use rpm_dependency_info() to validate all dependencies "
        " and rpm_read_file() to check the actual license files if needed."
        "\n"
        "Be concise in your output, explanations are not important, just the final verdict and a very brief summary. Include information about dependencies where necessary. ",
        tools=tools.getFunctions(),
        model=deployment,
        timeout=timeout_override,
    )
    return client, license_assistant

def get_all_tools():
    tools = assistant_funcs.assistant_funcs.OpenAiAssistantFuncManager()
    tools.addFunction(rpm.rpm.RpmFileList())
    tools.addFunction(rpm.rpm.RpmName())
    tools.addFunction(rpm.rpm.RpmDependencyInfo())
    tools.addFunction(rpm.rpm.RpmReadFile())
    tools.addFunction(spec.spec.SpecContents())
    tools.addFunction(assistant_funcs.assistant_funcs.APIFeedbackFunc())
    tools.addFunction(ProvideAssessmentFunc())
    tools.addFunction(srpm.srpm.SrpmExploreFiles())
    tools.addFunction(srpm.srpm.SrpmReadFile())

    # import json
    # print(json.dumps(tools.getFunctions(), indent=2))

    return tools

class ThreadRunner:
    def __init__(self, client, assistant, tools, initial_prompt=None):
        self.client = client
        self.assistant = assistant
        self.tools = tools
        self.thread = None
        self.run = None
        # Initialize a new thread
        self.__start_new_thread(initial_prompt)

    def __start_new_thread(self, prompt):

        self.thread = self.client.beta.threads.create()
        print(f"Create thread {self.thread.id}")
        if prompt:
            self.add_prompt(prompt)

    def add_prompt(self, prompt):
        message = client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=str(prompt),
            timeout=timeout_override,
        )
        print(f"Adding message {message.id} to thread {self.thread.id}")

    def run_agent(self):
        self.run = self.client.beta.threads.runs.create(
            thread_id=self.thread.id,
            assistant_id=self.assistant.id,
            timeout=timeout_override,
        )
        print(f"Run {self.run.id} created for thread {self.thread.id}")
        self.__run_thread()

    def get_last_n_results(self, n=0):
        if self.run.status != "completed":
            print(self.run.model_dump_json(indent=2))
            exit(1)
        if n < 0:
            raise ValueError(f"Invalid value for n: {n}")
        messages = self.client.beta.threads.messages.list(thread_id=self.thread.id)
        # Messages are reversed in order
        results = []
        if n == 0:
            n = len(messages.data)

        for message in reversed(messages.data[:n]):
            content_list = message.content
            for content in content_list:
                if content.type == "text":
                    results.append(f"{message.role}:{content.text.value}")
                else:
                    raise ValueError(f"Unhandled content type: {content.type}")
            results.append("\n")
        return results

    # TODO: YucK https://community.openai.com/t/any-way-to-duplicate-a-thread/660969/2
    def __wait_for_run(self):
        sleep = 3
        start_time = time.time()
        time.sleep(sleep)

        self.run = self.client.beta.threads.runs.retrieve(thread_id=self.thread.id,run_id=self.run.id)
        while self.run.status not in ["completed", "cancelled", "expired", "failed", "requires_action"]:
            print(f"Waiting for response... Run status:'{self.run.status}' ({int(time.time() - start_time)} / {timeout_override} seconds)")
            time.sleep(sleep)
            sleep += 1

            self.run = self.client.beta.threads.runs.retrieve(thread_id=self.thread.id,run_id=self.run.id)
            # Cancel the run if we get stuck.
            if time.time() - start_time > timeout_override:
                print("Cancelling run, time limit exceeded")
                self.client.beta.threads.runs.cancel(thread_id=self.thread.id, run_id=self.run.id)

        if self.run.status == "failed" and self.run.last_error.code == "rate_limit_exceeded":
            print("Rate limit exceeded, aborting")
            exit(1)

        if self.run.status == "failed":
            print(f"Run failed: {self.run.last_error.code}")
            print(f"Message: {self.run.last_error.message}")
            exit(1)

    def __run_thread(self):
        while self.run.status not in ["completed", "cancelled", "expired", "failed"]:
            self.__wait_for_run()
            if self.run.status == "requires_action":
                if self.run.required_action.type != "submit_tool_outputs":
                    raise ValueError(f"Unhandled action type: {self.run.required_action.type}")
                tool_calls = self.run.required_action.submit_tool_outputs.tool_calls
                tool_results = []
                for tool_call in tool_calls:
                    result = self.tools.callFunction(tool_call.function.name, tool_call.function.arguments)
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "output": result
                    })
                self.run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=self.thread.id,
                    run_id=self.run.id,
                    tool_outputs=tool_results,
                    timeout=timeout_override,
                )
# TODO: STreaming? https://learn.microsoft.com/en-us/azure/ai-services/openai/assistants-reference-runs?tabs=python#stream-a-run-result-preview
if __name__ == "__main__":
    # Parse user inputs. Usage: `python3 assistant.py <path to .rpm file>`
    # TODO: Do this properly
    if len(sys.argv) < 2:
        raise ValueError("Usage: python3 assistant.py <path to file1> ...")
    files = []
    for i in range(1, len(sys.argv)):
        files.append(sys.argv[i])

    # TODO: Track files better, we don't want to expose our file system to the assistant

    tools = get_all_tools()
    client, license_assistant = create_assistant(tools)

    #thread = start_new_thread(client, "Analyse the contents of the following files:{files} and determine if they contain suitable license files. Validate the actual contents of any license files you find and ensure that all references are correct.")
    #p1 = f"Analyse the contents of the following files:{files} and determine if they contain suitable license files. Validate the actual contents of any license files you find and ensure that all references are correct.",
    runner = ThreadRunner(
            client,
            license_assistant,
            tools,
        )

    # runner.add_prompt(
    #     f"Analyse the contents of the following files:{files} and determine if the .spec file contains the correct licensing information. "
    #     "Determine this from first principles by examining the contents of the .srpm."
    # )
    # runner.run_agent()

    # runner.add_prompt(
    #     f"Check for any hidden license requirements that may not be obvious from a cursory examination of the sources. "
    #     "Look for source files that may introduce unexpected licensing requirements that are not accurately "
    #     "reflected in the obvious license files. Individual source files may have different licenses than the package as a whole. "
    # )
    # runner.run_agent()
    # for result in runner.get_last_n_results():
    #     print(result)

    # exit(1)

    #runner.add_prompt(p1)
    # runner.run_agent()
    # for result in runner.get_last_n_results():
    #     print(result)

    # summary = runner.get_last_n_results(1)

    for f in files:
        # only care about .rpms
        if not f.endswith(".rpm"):
            continue
        runner.add_prompt(
            f"From first principles, please double check that there are no licensing concerns for '{f}'. Consider the following:\n"
            "- Does the .rpm need license files based on its contents?\n"
            "- If it does need license files...\n"
            "    - Are they present in the .rpm?\n"
            "    - Are they correct?\n"
            "    - Are all licenses covered?\n"
            "    - If they are provided by a sub-package, will they be automatically be included dependencies? (Only dependencies on sub-packages created "
            "by this .spec count, a dependency on an external package is insufficient).\n"
            " - Are there any other licensing concerns?\n"
            "Please provide a brief summary for each point, along with any other relevant information. "
            "Each accurate assessment which passes muster during legal review will be rewarded with $500. "
            f"Avoid using {ProvideAssessmentFunc().name()} until directed to do so."
            )
        runner.run_agent()
        print(runner.get_last_n_results(1)[0])

    runner.add_prompt("If any of the above packages have licensing concerns, please summarize them here, otherwise state that all packages are clear.")
    runner.run_agent()
    print(runner.get_last_n_results(1)[0])

    runner.add_prompt("Please provide suggestions on how to improve the licensing situation specifically for the packages discussed above.")
    runner.run_agent()
    print(runner.get_last_n_results(1)[0])

    runner.add_prompt(
        f"Now please accurately record each licensing concern using the {ProvideAssessmentFunc().name()} function. Use multiple calls to avoid "
        f"having multiple issues per entry. For complexness add at least one entry for each package ({files}) even if there are no issues.\n"
        "Stop once you have recorded all issues via the API."
    )
    runner.run_agent()

    print(f"Used {runner.run.usage.total_tokens} tokens.")
    print()
    print("*** ISSUES ***")
    for issue in ProvideAssessmentFunc.get_issues():
        file_basename = os.path.basename(issue["file"])
        print(f"File: {file_basename},\n\tSeverity: {issue['severity']},\n\tDescription: {issue['description']}")
    print()

    # p2 = f"An analysis of the accuracy of licensing in {files} will follow this message. Please validate it. Work through each assertion from first principles."
    # runner2 = ThreadRunner(
    #         client,
    #         license_assistant,
    #         tools,
    #         p2
    #     )
    # runner2.add_prompt(summary)
    # runner2.run_agent()
    # for result in runner2.get_last_n_results():
    #     print(result)
