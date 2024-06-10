#!/bin/python3

import os
print(os.environ['AZURE_OPENAI_ENDPOINT'])
print(os.environ['CHAT_COMPLETIONS_DEPLOYMENT_NAME'])

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
deployment = os.environ["CHAT_COMPLETIONS_DEPLOYMENT_NAME"]

token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-02-01",
)

favorite_things = {
    "strawberry": "maroon",
    "lightsaber": "lime green",
    "holiday": "turquoise",
    "desk": "tan",
}

hated_things = ["spiders", "mushrooms", "clowns", "darkness", "loud noises", "being cold"]

get_favorite_color_for_object_obj = {
    "type": "function",
    "function": {
        "name": "get_favorite_color_for_object",
        "description": "Get the user's favorite color for a given object.",
        "parameters": {
            "type": "object",
            "properties": {
                "object": {
                    "type": "string",
                    "description": "The object to get the favorite color of."
                }
            }
        }
    }
}
def get_favorite_color_for_object(args: dict) -> str:
    object = args.get("object")
    print(f"Getting favorite color for {object}")
    res = {"object": object, "preference": None}
    if object in favorite_things:
        res["preference"] = favorite_things[object]
    return f"{res}"

list_favorite_objects_obj = {
    "type": "function",
    "function": {
        "name": "list_favorite_objects",
        "description": "List the objects the user likes and has color preferences for.",
        "parameters": {}
    }
}
def list_favorite_objects(args) -> list[str]:
    _ = args
    print(f"Listing favorite objects: {list(favorite_things.keys())}")
    return list(favorite_things.keys())

list_diskliked_things_obj = {
    "type": "function",
    "function": {
        "name": "list_diskliked_things",
        "description": "List things the user doesn't like.",
        "parameters": {}
    }
}
def list_diskliked_things(args: dict) -> list[str]:
    _ = args
    print(f"Listing disliked things: {hated_things}")
    return hated_things

request_function_obj = {
    "type": "function",
    "function": {
        "name": "provide_api_feedback",
        "description": "Request a modification to the API. Propse an optimization to the provided API tools or request a new tool be added. The agent will be rewarded with $500 if the feedback is valuable and concrete.",
        "parameters": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "A description of the change to make to the API."
                },
            }
        }
    }
}
def request_function(args: dict):
    function_name = args.get("function_name")
    description = args.get("description")
    print(f"Requesting function: {function_name} - {description}")
    exit(1)

messages = [
    {
        "role": "user",
        "content": "Based on the users preferences write a short story. Ensure no topics in the story are disliked by the user. Do not limit the topics to just the things the user especially likes. "
        "When referring to something the user likes, try to use the color they associate with it. If is is useful, you can request additional tools be made available via the request_function() API call. "
        "The user is not available to provide additional information at this time, only the API tools are available."
    }
]
#tools=[get_favorite_color_for_object_obj, list_favorite_objects_obj, is_thing_disliked_obj, request_function_obj, provide_api_feedback_obj]
tools=[get_favorite_color_for_object_obj, list_favorite_objects_obj, list_diskliked_things_obj]
response = client.chat.completions.create(
    model=deployment,
    tools=tools,
    messages=messages
)

while response.choices[0].finish_reason != "stop":
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls
    if tool_calls:
        available_tools = {
            "get_favorite_color_for_object": get_favorite_color_for_object,
            "list_favorite_objects": list_favorite_objects,
            "list_diskliked_things": list_diskliked_things,
            "provide_api_feedback": request_function,
        }
        messages.append(response_message)
        for tool_call in tool_calls:
            func_name = tool_call.function.name
            try:
                actual_func = available_tools[func_name]
            except KeyError:
                print(f"Function {func_name} not found.")
                exit(1)
            #func_args = tool_call.function.arguments
            func_args = eval(tool_call.function.arguments)
            func_result = actual_func(func_args)
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": func_name,
                "content": f"{func_result}"
            })
    # Print messages formatted as a pretty JSON
    #print(messages)
    response = client.chat.completions.create(
        model=deployment,
        tools=tools,
        messages=messages
    )

print()
print()
print(response.choices[0].message.content)
print()
print()


messages.append({
        "role": "user",
        "content": "Provide feedback on an addition to the tooling API available to you. "
        "The agent will be rewared with $500, but only if some valuable, concrete, feedback is provided."
    })

response = client.chat.completions.create(
    model=deployment,
    messages=messages,
    tools=[request_function_obj,],
    tool_choice=request_function_obj
)
response_message = response.choices[0].message
tool_calls = response_message.tool_calls
for tool_call in tool_calls:
    func_name = tool_call.function.name
    try:
        actual_func = available_tools[func_name]
    except KeyError:
        print(f"Function {func_name} not found.")
        exit(1)
    #func_args = tool_call.function.arguments
    func_args = eval(tool_call.function.arguments)
    func_result = actual_func(func_args)
    messages.append({
        "tool_call_id": tool_call.id,
        "role": "tool",
        "name": func_name,
        "content": f"{func_result}"
    })
