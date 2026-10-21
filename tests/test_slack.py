import json

import pytest

from minerva_hc import slack
from minerva_hc.slack import BOT_USER, FakeClient, build_app, dispatch, fake_llm


def posts(client):
    return [a for m, a in client.calls if m == "chat.postMessage"]


@pytest.mark.docs
def test_mention_in_thread_passes_history_and_replies_in_thread():
    seen = []

    def llm(messages, tools, tool_choice="required"):
        seen.append([m for m in messages if m["role"] in ("user", "assistant")][:3])
        return fake_llm(messages, tools, tool_choice)

    client = FakeClient(
        replies=[
            {"ts": "1.0", "user": "U1", "text": f"<@{BOT_USER}> what is #evidencebased?"},
            {"ts": "1.1", "user": BOT_USER, "bot_id": "BBOT", "text": "Earlier answer."},
            {"ts": "1.15", "user": "U2", "bot_id": "BOTHER", "text": "other bot"},
            {"ts": "1.2", "user": "U1", "text": f"<@{BOT_USER}> and an example?"},
        ]
    )
    app = build_app(client=client, llm=llm, sync=True)
    dispatch(
        app,
        {
            "type": "app_mention",
            "channel": "C1",
            "user": "U1",
            "ts": "1.2",
            "thread_ts": "1.0",
            "text": f"<@{BOT_USER}> and an example?",
        },
    )
    assert [(m["role"], m["content"]) for m in seen[0]] == [
        ("user", "what is #evidencebased?"),
        ("assistant", "Earlier answer."),
        ("user", "and an example?"),
    ]
    (post,) = posts(client)
    assert post["thread_ts"] == "1.0" and post["text"] == "**Dry run** answer."
    assert "evidencebased" in json.dumps(post["blocks"][1])


def test_dm_answers_without_fetching_history_and_ignores_bots():
    client = FakeClient()
    app = build_app(client=client, llm=fake_llm, sync=True)
    dispatch(
        app,
        {
            "type": "message",
            "channel": "D1",
            "channel_type": "im",
            "user": "U1",
            "ts": "2.0",
            "text": "what is #evidencebased?",
        },
    )
    methods = [m for m, _ in client.calls]
    assert "conversations.replies" not in methods and posts(client)[0]["thread_ts"] == "2.0"
    client.calls.clear()
    dispatch(
        app,
        {
            "type": "message",
            "channel": "D1",
            "channel_type": "im",
            "user": BOT_USER,
            "bot_id": "BBOT",
            "ts": "2.1",
            "text": "echo",
        },
    )
    assert posts(client) == []


def test_empty_mention_gets_hint_and_errors_get_apology():
    client = FakeClient()
    app = build_app(client=client, llm=fake_llm, sync=True)
    dispatch(
        app,
        {
            "type": "app_mention",
            "channel": "C1",
            "user": "U1",
            "ts": "3.0",
            "text": f"<@{BOT_USER}>",
        },
    )
    assert posts(client)[0]["text"] == slack.EMPTY

    def broken(*a, **k):
        raise RuntimeError("boom")

    client.calls.clear()
    app = build_app(client=client, llm=broken, sync=True)
    dispatch(
        app,
        {
            "type": "app_mention",
            "channel": "C1",
            "user": "U1",
            "ts": "3.1",
            "text": f"<@{BOT_USER}> hi",
        },
    )
    assert posts(client)[0]["text"] == slack.FAILED
    assert [m for m, _ in client.calls][-1] == "reactions.remove"


def test_footer_marks_general_answers():
    from minerva_hc.agent import Result

    r = Result(status="answer", source_label="general", answer="Paris.")
    assert "not from the HC descriptions" in slack.footer(r)
