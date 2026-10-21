from minerva_hc.llm import to_choice, to_input, to_tool
from minerva_hc.tools import TOOLS

CALL = {"type": "function_call", "call_id": "c1", "name": "read_file", "arguments": "{}"}


def test_to_input():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "_items": [{"type": "reasoning"}, CALL]},
        {"role": "tool", "tool_call_id": "c1", "content": "doc"},
    ]
    instructions, items = to_input(messages)
    assert instructions == "sys"
    assert items == [
        {"role": "user", "content": "q"},
        {"type": "reasoning"},
        CALL,
        {"type": "function_call_output", "call_id": "c1", "output": "doc"},
    ]


def test_tool_and_choice():
    assert to_tool(TOOLS[0])["name"] == "read_file"
    assert to_tool(TOOLS[0])["type"] == "function"
    assert to_choice("required") == "required"
    forced = {"type": "function", "function": {"name": "final_answer"}}
    assert to_choice(forced) == {"type": "function", "name": "final_answer"}
