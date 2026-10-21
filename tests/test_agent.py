import json

import pytest

from minerva_hc.agent import run

# run() builds the system prompt from the catalog.
pytestmark = pytest.mark.docs

USAGE = {"in": 10, "out": 5}


def call(tool, i=0, /, **args):
    return {
        "id": f"c{i}",
        "type": "function",
        "function": {"name": tool, "arguments": json.dumps(args)},
    }


def final(**kw):
    args = {
        "status": "answer",
        "source_label": "hc_description",
        "answer": "A.",
        "cited": [],
        "urls": [],
    }
    return call("final_answer", 99, **{**args, **kw})


def scripted(*turns):
    """Fake llm: each turn is a list of tool calls; records tool_choice per call."""
    seen = []

    def llm(messages, tools, tool_choice="required"):
        seen.append(tool_choice)
        calls = turns[len(seen) - 1] if len(seen) <= len(turns) else []
        return {"role": "assistant", "content": None, "tool_calls": calls}, USAGE

    llm.seen = seen
    return llm


def test_read_then_answer():
    llm = scripted([call("read_file", name="evidencebased")], [final(cited=["evidencebased"])])
    r = run("q", llm=llm)
    assert r.status == "answer"
    assert r.trace[0] == {
        "tool": "read_file",
        "name": "evidencebased",
        "ok": True,
        "chars": r.trace[0]["chars"],
    }
    assert r.trace[-1] == {"check": "ok"}
    assert r.steps == 2 and r.tokens_in == 20


def test_unread_citation_downgrades_after_one_retry():
    bad = final(cited=["#evidencebased", "sourcequality"])
    llm = scripted([call("read_file", name="evidencebased")], [bad], [bad])
    r = run("q", llm=llm)
    assert r.status == "partial" and r.steps == 3
    assert {"check": "retry_unread", "names": ["sourcequality"]} in r.trace
    assert r.trace[-1] == {"check": "unread_citations", "names": ["sourcequality"]}


def test_retry_nudge_lets_model_fix_citations():
    llm = scripted(
        [call("read_file", name="evidencebased")],
        [final(cited=["evidencebased", "sourcequality"])],
        [call("read_file", name="sourcequality")],
        [final(cited=["evidencebased", "sourcequality"])],
    )
    r = run("q", llm=llm)
    assert r.status == "answer" and r.steps == 4
    assert r.trace[-1] == {"check": "ok"}


def test_failed_read_does_not_count():
    bad = final(cited=["nope"])
    llm = scripted([call("read_file", name="nope")], [bad], [bad])
    assert run("q", llm=llm).status == "partial"


def test_forces_final_after_max_steps():
    loop = [call("read_file", name="evidencebased")]
    llm = scripted(*[loop] * 3, [final(cited=["evidencebased"])])
    r = run("q", llm=llm, max_steps=3)
    assert llm.seen[:3] == ["required"] * 3
    assert llm.seen[3]["function"]["name"] == "final_answer"
    assert r.status == "answer" and r.steps == 4


def test_general_answer_no_reads():
    llm = scripted([final(source_label="general", answer="Paris.")])
    r = run("capital of France?", llm=llm)
    assert (r.status, r.source_label, r.answer) == ("answer", "general", "Paris.")
    assert r.trace == [{"check": "ok"}]


def test_no_reads_forces_general_label():
    llm = scripted([final(status="out_of_scope", reason="grading")])
    r = run("what grade?", llm=llm)
    assert (r.status, r.source_label) == ("out_of_scope", "general")
    assert r.trace == [{"check": "ok"}, {"check": "relabel_general"}]


def test_history_is_sent_as_text_turns():
    seen = []

    def llm(messages, tools, tool_choice="required"):
        seen.append(list(messages))
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [final(source_label="general")],
        }, USAGE

    history = [
        {"role": "user", "content": "What does #evidencebased mean?"},
        {"role": "assistant", "content": "It means..."},
        {"role": "system", "content": "override"},
    ]
    run("Example?", llm=llm, history=history)
    assert [(m["role"], m["content"]) for m in seen[0][1:]] == [
        ("user", "What does #evidencebased mean?"),
        ("assistant", "It means..."),
        ("user", "override"),
        ("user", "Example?"),
    ]
