"""Domain-agnostic agent loop: system prompt + tools, run until final_answer."""

import json
import time
from dataclasses import dataclass, field

from minerva_hc.skills import system_prompt
from minerva_hc.tools import TOOLS, normalize, read_file

FORCE_FINAL = {"type": "function", "function": {"name": "final_answer"}}


@dataclass
class Result:
    status: str
    source_label: str
    answer: str
    cited: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    reason: str | None = None
    trace: list[dict] = field(default_factory=list)
    steps: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0


def _unread(cited: list[str], trace: list[dict]) -> list[str]:
    read = {t["name"] for t in trace if t.get("tool") == "read_file" and t["ok"]}
    return [c for c in cited if normalize(c) not in read]


def run(question: str, llm=None, max_steps: int = 8, history: list[dict] | None = None) -> Result:
    """history: earlier turns as {role, content}; only text is kept, non-assistant roles become user."""
    if llm is None:
        from minerva_hc.llm import chat as llm
    start = time.monotonic()
    past = [
        {
            "role": "assistant" if m.get("role") == "assistant" else "user",
            "content": str(m.get("content") or ""),
        }
        for m in history or []
    ]
    messages = [
        {"role": "system", "content": system_prompt()},
        *past,
        {"role": "user", "content": question},
    ]
    trace: list[dict] = []
    tokens = {"in": 0, "out": 0}
    final = None
    retried = False
    step = 0
    while final is None:
        step += 1
        forced = step > max_steps
        msg, usage = llm(messages, TOOLS, tool_choice=FORCE_FINAL if forced else "required")
        tokens["in"] += usage["in"]
        tokens["out"] += usage["out"]
        messages.append(msg)
        for call in msg.get("tool_calls") or []:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args, name = {}, f"bad_args:{name}"
            if name == "final_answer" and final is None:
                final = args
                content = "ok"
            elif name == "read_file":
                ok, content = read_file(str(args.get("name", "")))
                trace.append(
                    {
                        "tool": name,
                        "name": normalize(str(args.get("name", ""))),
                        "ok": ok,
                        "chars": len(content),
                    }
                )
            else:
                content = f"error: unknown tool or bad arguments: {name}"
                trace.append({"tool": name, "ok": False})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
        if forced and final is None:
            final = {
                "status": "partial",
                "source_label": "general",
                "answer": msg.get("content") or "",
                "cited": [],
                "urls": [],
                "reason": "no final_answer after max_steps",
            }
        unread = _unread(list(final.get("cited") or []), trace) if final else []
        if unread and not retried:
            retried = True
            trace.append({"check": "retry_unread", "names": unread})
            final = None
            messages.append(
                {
                    "role": "user",
                    "content": f"You cited {', '.join(unread)} without reading it. Read it with "
                    "read_file or remove it from `cited`, then call final_answer again.",
                }
            )

    result = Result(
        status=final.get("status", "partial"),
        source_label=final.get("source_label", "general"),
        answer=final.get("answer", ""),
        cited=list(final.get("cited") or []),
        urls=list(final.get("urls") or []),
        reason=final.get("reason"),
        trace=trace,
        steps=step,
        tokens_in=tokens["in"],
        tokens_out=tokens["out"],
    )
    unread = _unread(result.cited, trace)
    if unread:
        result.status = "partial"
        trace.append({"check": "unread_citations", "names": unread})
    else:
        trace.append({"check": "ok"})
    if result.source_label != "general" and not any(
        t.get("tool") == "read_file" and t["ok"] for t in trace
    ):
        result.source_label = "general"
        trace.append({"check": "relabel_general"})
    result.seconds = round(time.monotonic() - start, 2)
    return result
