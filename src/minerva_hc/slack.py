"""Slack adapter: @mentions and DMs → agent.run, answered in a thread (Socket Mode)."""

import json
import logging
import os
import re

from slack_bolt import App
from slack_bolt.request import BoltRequest
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.web import SlackResponse

from minerva_hc import agent

log = logging.getLogger(__name__)
MENTION = re.compile(r"<@[A-Z0-9]+>")
MAX_CHARS = 11_000  # markdown blocks share a 12k-char limit per message
MAX_TURNS = 20
WORKING = "eyes"
EMPTY = "Ask me about an HC, e.g. _What does #evidencebased mean?_"
FAILED = "Sorry, something went wrong while answering. Please try again."


def clean(text: str | None) -> str:
    return MENTION.sub("", text or "").strip()


def thread_history(client, channel: str, thread_ts: str, current_ts: str, bot_user_id: str):
    """Earlier thread messages as {role, content}. Bot replies' `text` excludes the footer block."""
    msgs = client.conversations_replies(channel=channel, ts=thread_ts, limit=100)["messages"]
    turns = []
    for m in msgs:
        mine = m.get("user") == bot_user_id
        if m.get("ts") == current_ts or (m.get("bot_id") and not mine):
            continue
        text = m.get("text", "") if mine else clean(m.get("text"))
        if text:
            turns.append({"role": "assistant" if mine else "user", "content": text})
    return turns[-MAX_TURNS:]


def footer(r: agent.Result) -> str:
    parts = [f"{r.status} · {r.source_label}"]
    links = [
        f"<{url}|#{name.lstrip('#')}>" if url else f"#{name.lstrip('#')}"
        for name, url in zip(r.cited, r.urls + [""] * len(r.cited))
    ]
    if links:
        parts.append(" ".join(links))
    if r.source_label == "general":
        parts.append("general knowledge, not from the HC descriptions")
    return "  |  ".join(parts)


def blocks(r: agent.Result) -> list[dict]:
    return [
        {"type": "markdown", "text": r.answer[:MAX_CHARS] or "_(no answer)_"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": footer(r)}]},
    ]


def _react(method, **kw) -> None:
    try:
        method(**kw)
    except SlackApiError as e:
        log.warning("reaction failed: %s", e.response.get("error"))


def respond(event: dict, client, bot_user_id: str, llm=None) -> None:
    channel, ts = event["channel"], event["ts"]
    thread_ts = event.get("thread_ts") or ts
    question = clean(event.get("text"))
    if not question:
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=EMPTY)
        return
    _react(client.reactions_add, channel=channel, timestamp=ts, name=WORKING)
    try:
        past = []
        if event.get("thread_ts"):
            past = thread_history(client, channel, thread_ts, ts, bot_user_id)
        r = agent.run(question, llm=llm, history=past)
        log.info("answered %s/%s: %s %s %ss", channel, ts, r.status, r.source_label, r.seconds)
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=r.answer[:MAX_CHARS], blocks=blocks(r)
        )
    except Exception:
        log.exception("answer failed for %s/%s", channel, ts)
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=FAILED)
    finally:
        _react(client.reactions_remove, channel=channel, timestamp=ts, name=WORKING)


def build_app(token: str | None = None, client=None, llm=None, sync: bool = False) -> App:
    """Validates the token (auth.test) at startup. sync=True runs listeners inside dispatch.

    Listeners use app.client rather than Bolt's per-request client, so a fake client covers every call.
    """
    app = App(client=client or WebClient(token=token), process_before_response=sync)

    @app.event("app_mention")
    def on_mention(event, context):
        if not event["channel"].startswith("D"):  # DMs are handled by on_message
            respond(event, app.client, context.bot_user_id, llm)

    @app.event("message")
    def on_message(event, context):
        if (
            event.get("channel_type") == "im"
            and not event.get("subtype")
            and not event.get("bot_id")
        ):
            respond(event, app.client, context.bot_user_id, llm)

    return app


def serve() -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    bot, app_token = _tokens()
    missing = [k for k, v in (("SLACK_BOT_TOKEN", bot), ("SLACK_APP_TOKEN", app_token)) if not v]
    if missing:
        raise SystemExit(f"missing in .env: {', '.join(missing)} (see README, Slack bot)")
    SocketModeHandler(build_app(bot), app_token).start()


# --- dry run: config checks + one fake event end to end, no Slack or OpenAI calls ---

BOT_USER = "UBOT"


class FakeClient(WebClient):
    """Records Web API calls instead of sending them."""

    def __init__(self, replies: list[dict] | None = None):
        super().__init__(token="xoxb-fake")
        self.calls: list[tuple[str, dict]] = []
        self.replies = replies or []

    def api_call(self, api_method, **kwargs):
        args = {**(kwargs.get("params") or {}), **(kwargs.get("json") or {})}
        args.update(kwargs.get("data") or {})
        self.calls.append((api_method, args))
        data = {"ok": True}
        if api_method == "auth.test":
            data |= {"user_id": BOT_USER, "bot_id": "BBOT", "team_id": "T1", "user": "minerva-hc"}
        elif api_method == "conversations.replies":
            data["messages"] = self.replies
        return SlackResponse(
            client=self,
            http_verb="POST",
            api_url=api_method,
            req_args=kwargs,
            data=data,
            headers={},
            status_code=200,
        )


def fake_llm(messages, tools, tool_choice="required"):
    """Reads evidencebased once, then answers citing it."""
    read = any(m.get("role") == "tool" for m in messages)
    name, args = (
        (
            "final_answer",
            {
                "status": "answer",
                "source_label": "hc_description",
                "answer": "**Dry run** answer.",
                "cited": ["evidencebased"],
                "urls": ["https://example.org/evidencebased"],
            },
        )
        if read
        else ("read_file", {"name": "evidencebased"})
    )
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }
    return {"role": "assistant", "content": None, "tool_calls": [call]}, {"in": 0, "out": 0}


def event_body(event: dict) -> dict:
    return {"type": "event_callback", "team_id": "T1", "api_app_id": "A1", "event": event}


def dispatch(app: App, event: dict):
    return app.dispatch(BoltRequest(body=json.dumps(event_body(event)), mode="socket_mode"))


def _tokens() -> tuple[str, str]:
    from dotenv import load_dotenv

    load_dotenv()
    return os.environ.get("SLACK_BOT_TOKEN", ""), os.environ.get("SLACK_APP_TOKEN", "")


def dry_run() -> bool:
    ok = True

    def check(passed: bool, label: str, hint: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(
            f"  {'ok  ' if passed else 'FAIL'} {label}"
            + (f": {hint}" if hint and not passed else "")
        )

    print("config")
    bot, app_token = _tokens()
    check(bot.startswith("xoxb-"), "SLACK_BOT_TOKEN", "missing or not xoxb- (OAuth & Permissions)")
    check(
        app_token.startswith("xapp-"), "SLACK_APP_TOKEN", "missing or not xapp- (Basic Information)"
    )
    check(bool(os.environ.get("OPENAI_API_KEY")), "OPENAI_API_KEY")

    print("fake events (no network)")
    client = FakeClient(
        replies=[
            {"ts": "1.0", "user": "U1", "text": f"<@{BOT_USER}> what is #evidencebased?"},
            {"ts": "1.1", "user": BOT_USER, "bot_id": "BBOT", "text": "Earlier answer."},
            {"ts": "1.2", "user": "U1", "text": f"<@{BOT_USER}> and an example?"},
        ]
    )
    app = build_app(client=client, llm=fake_llm, sync=True)
    resp = dispatch(
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
    posts = [a for m, a in client.calls if m == "chat.postMessage"]
    check(resp.status == 200, "mention dispatched", f"status {resp.status}")
    check(
        len(posts) == 1 and posts[0].get("thread_ts") == "1.0", "threaded reply posted", str(posts)
    )
    check(
        bool(posts) and "evidencebased" in json.dumps(posts[0].get("blocks")), "footer cites the HC"
    )
    check(any(m == "conversations.replies" for m, _ in client.calls), "thread history fetched")
    methods = [m for m, _ in client.calls]
    check(
        "reactions.add" in methods and "reactions.remove" in methods,
        "working reaction added/removed",
    )

    client.calls.clear()
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
    check(any(m == "chat.postMessage" for m, _ in client.calls), "DM answered")
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
            "text": "bot echo",
        },
    )
    check(not any(m == "chat.postMessage" for m, _ in client.calls), "own messages ignored")

    if bot.startswith("xoxb-") and app_token.startswith("xapp-"):
        print("live token check (read-only)")
        try:
            who = WebClient(token=bot).auth_test()
            check(True, f"bot token: {who['user']} in {who['team']}")
        except SlackApiError as e:
            check(False, "bot token", e.response.get("error"))
        try:
            WebClient(token=app_token).apps_connections_open(app_token=app_token)
            check(True, "app token: Socket Mode connection allowed")
        except SlackApiError as e:
            check(False, "app token", e.response.get("error"))
    print("dry run passed" if ok else "dry run FAILED")
    return ok
