"""Thin OpenAI Responses API wrapper.

The agent speaks chat-style dicts (system/user/assistant+tool_calls/tool); this module translates
them to Responses input items and back, so the agent and tests stay SDK-free. Raw output items
(including reasoning) ride along on the assistant message under "_items" and are replayed as-is.
"""

import os
from functools import cache

from dotenv import load_dotenv


@cache
def client():
    from openai import OpenAI

    load_dotenv()
    return OpenAI()


def to_input(messages: list[dict]) -> tuple[str | None, list[dict]]:
    instructions, items = None, []
    for m in messages:
        if m["role"] == "system":
            instructions = m["content"]
        elif m["role"] == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": m["tool_call_id"],
                    "output": m["content"],
                }
            )
        elif "_items" in m:
            items.extend(m["_items"])
        else:
            items.append({"role": m["role"], "content": m["content"] or ""})
    return instructions, items


def to_tool(tool: dict) -> dict:
    return {"type": "function", **tool["function"]}


def to_choice(choice):
    if isinstance(choice, dict):
        return {"type": "function", "name": choice["function"]["name"]}
    return choice


def chat(messages: list[dict], tools: list[dict], tool_choice="required") -> tuple[dict, dict]:
    instructions, items = to_input(messages)
    resp = client().responses.create(
        model=os.environ["OPENAI_MODEL"],
        instructions=instructions,
        input=items,
        tools=[to_tool(t) for t in tools],
        tool_choice=to_choice(tool_choice),
    )
    raw = [item.model_dump(exclude_none=True) for item in resp.output]
    calls = [
        {
            "id": i["call_id"],
            "type": "function",
            "function": {"name": i["name"], "arguments": i["arguments"]},
        }
        for i in raw
        if i["type"] == "function_call"
    ]
    msg = {"role": "assistant", "content": resp.output_text or None, "_items": raw}
    if calls:
        msg["tool_calls"] = calls
    return msg, {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}
