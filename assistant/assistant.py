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
    __provide_assessment_name = "provide_assessment"
    __provide_assessment_description = "Provide an assessment of the licensing situation for the provided packages."
    __provide_assessment_parameters = {
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
        super().__init__(self.__provide_assessment_name, self.__provide_assessment_description, self.__provide_assessment_parameters)

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

class RequestAnalysis(assistant_funcs.assistant_funcs.OpenAIAssistantFunc):
    analysis_list = []
    __request_analysis_Name = "request_analysis"
    __request_analysis_Description = "Mark a file for further inspection"
    __request_analysis_Parameters = {
        "file": {
            "type": "string",
            "description": "REQUIRED: The file to investigate further."
        },
    }

    def __init__(self) -> None:
        super().__init__(self.__request_analysis_Name, self.__request_analysis_Description, self.__request_analysis_Parameters)

    def call(self, file) -> str:
        if not file:
            return "File is required."
        self.analysis_list.append(file)
        return f"Assessment for '{file}' added."

    def get_files():
        return RequestAnalysis.analysis_list


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
        " (e.g. a '-devel' package may require the license file from the main package, or a main package may use the license files from a '-libs' subpackage) "
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
    tools.addFunction(srpm.srpm.SrpmExploreFiles())
    tools.addFunction(srpm.srpm.SrpmReadFile())
    tools.addFunction(assistant_funcs.assistant_funcs.APIFeedbackFunc())
    tools.addFunction(ProvideAssessmentFunc())
    tools.addFunction(RequestAnalysis())

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
        self.last_line_printed_idx = None
        # Initialize a new thread
        self.__start_new_thread(initial_prompt)

    def __start_new_thread(self, prompt):

        self.thread = self.client.beta.threads.create()
        if prompt:
            self.add_prompt(prompt)

    def add_prompt(self, prompt):
        message = client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=str(prompt),
            timeout=timeout_override,
        )

    def run_agent(self, force_tool=None):
        if not force_tool:
            tool_selection = "auto"
        else:
            tool_selection = force_tool.choice()
        self.run = self.client.beta.threads.runs.create(
            thread_id=self.thread.id,
            assistant_id=self.assistant.id,
            timeout=timeout_override,
            tool_choice=tool_selection,
        )
        self.__run_thread()

    def get_new_results(self):
        # Print all the results we haven't seen yet.
        results = self.get_last_n_results()
        if self.last_line_printed_idx:
            results = results[self.last_line_printed_idx:]
        self.last_line_printed_idx = len(results)
        return results

    def get_last_n_results(self, n=0, include_names=True):
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
                    if include_names:
                        result_string = f"{message.role}:"
                        for line in  content.text.value.split("\n"):
                            result_string += f"\n>\t{line}"
                        results.append(result_string)
                    else:
                        results.append(content.text.value)
                else:
                    raise ValueError(f"Unhandled content type: {content.type}")
            results.append("\n")
        return results

    # TODO: YucK https://community.openai.com/t/any-way-to-duplicate-a-thread/660969/2
    def __wait_for_run(self):
        sleep = 1
        start_time = time.time()
        time.sleep(sleep)

        self.run = self.client.beta.threads.runs.retrieve(thread_id=self.thread.id,run_id=self.run.id)
        while self.run.status not in ["completed", "cancelled", "expired", "failed", "requires_action"]:
            time_elapsed = int(time.time() - start_time)
            if time_elapsed % 10 == 0:
                print(f"Waiting for response... Run status:'{self.run.status}' ({time_elapsed} / {timeout_override} seconds)")
            time.sleep(sleep)

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

# TODO: Test of a deepscanner, WIP
def deepscan_testing(client, license_assistant, tools, files):
    deep_scan_runner = ThreadRunner(
            client,
            license_assistant,
            tools,
        )
    analysis_runner = ThreadRunner(
            client,
            license_assistant,
            tools,
        )
    srpm_files = [f for f in files if f.endswith(".src.rpm")]
    deep_scan_runner.add_prompt(
        f"Analyse the contents of the following files:'{srpm_files}' and decide if any files need investigation. The end goal is "
        "to decide if the licensing information for the project is correct. A separate agent will be responsible for making the final "
        "assessment. Your job is to identify any files that might affect the licensing situation as quickly as possible. Be selective, "
        " each analysis may be time consuming. Pick only those files that are likely to cause issues with licensing. If required "
        f" you may examine a file in detail with the {srpm.srpm.SrpmReadFile().name()} function to ensure the files are actually interesting. "
        "Consider marking suspect source files for analysis, to see if their headers match the expected licenses (be selective however). Feel free to investigate "
        "some files to determine what they are for, if you aren't sure, but again do try to be selective."
    )
    analysis_runner.add_prompt(
        f"Another agent is generating a list of interesting files to investigate which are from {srpm_files}. Please determine from first principles what the required licensing situation is for this package. "
        " Do not assume that the current licensing files are sufficient, there may be hidden additional licensing requirements. You may investigate the source files as needed, even "
        " those that are not flagged by the other agent."
    )
    src_files = srpm.srpm.SrpmExploreFiles().srpm_explore_contents(srpm_file="nano.src.rpm", search_dir=".", max_depth=0)
    # remove anything that doesn't start with 'file:', and remove the 'file:' prefix
    src_files = [f.removeprefix("file:") for f in src_files if f.startswith("file:")]
    # Split the files into groups
    group_size = 30
    grouped_files = [src_files[i:i + group_size] for i in range(0, len(src_files), group_size)]

    for g in grouped_files:
        print(g)
        deep_scan_runner.add_prompt(
            f"Should any of the following files be investigated further? Indicate any positive results via the {RequestAnalysis().name()} function. {g}"
        )
        deep_scan_runner.run_agent()

    groups_requests = [RequestAnalysis.get_files()[i:i + group_size] for i in range(0, len(RequestAnalysis.get_files()), group_size)]
    for r in groups_requests:
        print(r)
        analysis_runner.add_prompt(
            f"The other agent thought the following files were interesting: {r}. Determine if they have any licensing concerns. Hold a full review for later, you will be asked "
            "specifically to provide one when needed. Most importantly, ensure that you have an accurate list of all the licenses used in the package."
        )
        analysis_runner.run_agent()

    print("\n\n**** DEEP SCAN RESULTS ****\n")
    analysis_runner.add_prompt(
        f"Complete a full review, then provide a summary of the licensing situation for the files: {srpm_files}. "
    )
    analysis_runner.run_agent()

    for l in analysis_runner.get_new_results():
        print(l)

    analysis_runner.add_prompt(f"Check if the package {files} match the expected licenses you found. Submit any issues via the {ProvideAssessmentFunc().name()} function. "
                               "The package is not trusted, your job is to validate that is correct.")
    analysis_runner.run_agent()
    for l in analysis_runner.get_new_results():
        print(l)

# TODO: STreaming? https://learn.microsoft.com/en-us/azure/ai-services/openai/assistants-reference-runs?tabs=python#stream-a-run-result-preview
if __name__ == "__main__":
    # Parse user inputs. Usage: `python3 assistant.py <path to .rpm file>`
    # TODO: Do this properly
    do_deepscan = "--deepscan" in sys.argv
    args = [a for a in sys.argv if not a.startswith("--")]
    if len(args) < 2:
        raise ValueError("Usage: python3 assistant.py <path to file1> ...")
    files = args[1:]
    print(files)
    # TODO: Track files better, we don't want to expose our file system to the assistant

    tools = get_all_tools()
    client, license_assistant = create_assistant(tools)

    if do_deepscan:
        deepscan_testing(client, license_assistant, tools, files)
        exit(0)

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

    print(f"\n\n**** CONSIDERING FILES ****\n")
    for f in files:
        print(f"\t{f}")

    package_results_text = {}
    for f in files:
        # only care about .rpms
        if not f.endswith(".rpm") or f.endswith(".src.rpm"):
            continue
        print(f"\n\n**** EXAMINING {f} ****\n")
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
        package_results_text[f] = runner.get_last_n_results(1,False)[0]

    print("\n\n**** GENERATING SUMMARY ****\n")

    runner.add_prompt("If any of the above packages have licensing concerns, please summarize them here, otherwise state that all packages are clear.")
    runner.run_agent()
    summary_text = runner.get_last_n_results(1,False)[0]

    print("\n\n**** GENERATING SUGGESTIONS ****\n")

    runner.add_prompt("Please provide suggestions on how to improve the licensing situation specifically for the packages discussed above.")
    runner.run_agent()
    suggestions_text = runner.get_last_n_results(1,False)[0]

    print("\n\n**** GATHERING ISSUES ****\n")

    runner.add_prompt(
        f"Now please accurately record each licensing concern using the {ProvideAssessmentFunc().name()} function. Use multiple calls to avoid\n"
        f"having multiple issues per entry. For complexness add at least one entry for each package ({files}) even if there are no issues.\n"
        "Stop once you have recorded all issues via the API."
    )
    runner.run_agent()

    print("\n\n**** SUMMARY ****\n")
    print(f"\tUsed {runner.run.usage.total_tokens} tokens.\n")
    print(summary_text)

    print("\n\n**** SUGGESTIONS ****\n")
    print(suggestions_text)

    print("\n\n**** ISSUES ****\n")
    for issue in ProvideAssessmentFunc.get_issues():
        file_basename = os.path.basename(issue["file"])
        print(f"File: {file_basename},\n\tSeverity: {issue['severity']},\n\tDescription: {issue['description']}")
    print()


    summary_path = "summary.txt"
    print(f"\n\n**** SAVING CONVERSATION TO {summary_path} ****\n")
    with open(summary_path, "w") as f:
        f.write(f"Findings for {files}:\n")
        for issue in ProvideAssessmentFunc.get_issues():
            file_basename = os.path.basename(issue["file"])
            f.write(f"File: {file_basename},\n\tSeverity: {issue['severity']},\n\tDescription: {issue['description']}\n")
        f.write("\n")
        f.write("Conversation:\n")
        f.writelines(runner.get_last_n_results())

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

    # runner.add_prompt(f"Please provide feedback on the API so this process can be improved for next time. Be honest, but constructive. "
    #                   "Try to find at least 4 meaty, actionable points that would improve accuracy or performance. "
    #                   "Use the {assistant_funcs.assistant_funcs.APIFeedbackFunc().name()} function for each bit of feedback."
    #                   )
    # runner.run_agent(force_tool=assistant_funcs.assistant_funcs.APIFeedbackFunc())
