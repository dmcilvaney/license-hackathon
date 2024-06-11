#!/bin/python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import sys
import time

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

import rpm.rpm
import assistant_funcs.assistant_funcs

# Parse user inputs. Usage: `python3 assistant.py <path to .rpm file>`
# TODO: Do this properly
if len(sys.argv) != 2:
    raise ValueError("Usage: python3 assistant.py <path to .rpm file>")
rpm_file = sys.argv[1]

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
)

tools = assistant_funcs.assistant_funcs.OpenAiAssistantFuncManager()
tools.addFunction(rpm.rpm.RpmFileList())
feedbackTool = assistant_funcs.assistant_funcs.APIFeedbackFunc()
tools.addFunction(feedbackTool)

import json
print(json.dumps(tools.getFunctions(), indent=2))

# https://platform.openai.com/docs/api-reference/assistants/createAssistant
license_assistant = client.beta.assistants.create(
    name="License Assistant",
    instructions=f"You are a very skilled AI assistant that specializes in working with open source project licenses. "
    f"You have access to a sandbox environment where you can investigate a .rpm file, the .src.rpm it was generated from, and the .spec file used to generate it. "
    f"Your goal is to determine if all .rpm files have suitable license files included in them, and if the license files are correct. "
    f"You may access the contents of the .rpm file, the .src.rpm file, and the .spec file via the provided functions.",
    tools=tools.getFunctions(),
    model=deployment,
    timeout=600,
)

thread = client.beta.threads.create()

message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content=f"Analyse the contents of the .rpm file {rpm_file} and determine if it contains suitable license files."
)

run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=license_assistant.id,
)

# TODO: YucK https://community.openai.com/t/any-way-to-duplicate-a-thread/660969/2
def wait_for_run(run):
    # Throttle the rate of requests
    time.sleep(1)
    run = client.beta.threads.runs.retrieve(thread_id=thread.id,run_id=run.id)
    status = run.status

    sleep = 1
    while status not in ["completed", "cancelled", "expired", "failed", "requires_action"]:
        time.sleep(sleep)
        sleep += 1
        run = client.beta.threads.runs.retrieve(thread_id=thread.id,run_id=run.id)
        status = run.status
        print(f"Run status: {status}")

    if run.status == "failed" and run.last_error.code == "rate_limit_exceeded":
        # Error will be of the form "Rate limit exceeded. Please try again in <NUMBER> seconds."
        # Try to parse the number of seconds and sleep for that amount of time.
        sleepTime = int(run.last_error.message.split(" ")[-2]) + 5

        print(f"Rate limit exceeded, retrying in {sleepTime} seconds")
        time.sleep(sleepTime)

        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=license_assistant.id,
        )


    return run

while run.status not in ["completed", "cancelled", "expired", "failed"]:
    run = wait_for_run(run)
    if run.status == "requires_action":
        if run.required_action.type != "submit_tool_outputs":
            raise ValueError(f"Unhandled action type: {run.required_action.type}")
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_results = []
        for tool_call in tool_calls:
            result = tools.callFunction(tool_call.function.name, tool_call.function.arguments)
            tool_results.append({
                "tool_call_id": tool_call.id,
                "output": result
            })
        run = client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread.id,
            run_id=run.id,
            tool_outputs=tool_results
        )
# Dump run:
print(run.model_dump_json(indent=2))

# Messages:
messages = client.beta.threads.messages.list(thread_id=thread.id)
for message in messages:
    print(f"{message.role}: {message.content}")

message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content=f"Having analyzed the contents of the .rpm file, please provide feedback on the API."
)
run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=license_assistant.id,
    tool_choice=feedbackTool.choice()
)
run = wait_for_run(run)
if not run.status == "requires_action":
    raise ValueError(f"Unexpected run status: {run.status}")
if run.required_action.type != "submit_tool_outputs":
    raise ValueError(f"Unexpected action type: {run.required_action.type}")

tool_calls = run.required_action.submit_tool_outputs.tool_calls
for tool_call in tool_calls:
    tools.callFunction(tool_call.function.name, tool_call.function.arguments)
