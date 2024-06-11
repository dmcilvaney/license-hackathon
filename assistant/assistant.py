#!/bin/python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import time
print(os.environ['AZURE_OPENAI_ENDPOINT'])
print(os.environ['CHAT_COMPLETIONS_DEPLOYMENT_NAME'])

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

import rpm.rpm
import assistant_funcs.assistant_funcs

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
deployment = os.environ["CHAT_COMPLETIONS_DEPLOYMENT_NAME"]

token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-05-01-preview",
)

tools = assistant_funcs.assistant_funcs.OpenAiAssistantFuncManager()
tools.addFunction(rpm.rpm.RpmFileList())

import json
print(json.dumps(tools.getFunctions(), indent=2))

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

rpm_file = "../nano-testing/rpms/nano-6.0-2.cm2.x86_64.rpm"

message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content=f"Analyse the contents of the .rpm file {rpm_file} and determine if it contains suitable license files."
)

run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=license_assistant.id,
)

def wait_for_run(run):
    run = client.beta.threads.runs.retrieve(thread_id=thread.id,run_id=run.id)
    status = run.status
    while status not in ["completed", "cancelled", "expired", "failed", "requires_action"]:
        print(f"Run status: {run.status}")
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id,run_id=run.id)
        status = run.status
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
