# minerva-hc

An LLM agent that answers questions about Minerva's HCs (Habits of Mind and Foundational Concepts). It reads
the full HC description docs instead of searching chunks, and cites the HCs it used.

It can:

- **Explain** an HC (`What does #evidencebased mean?`)
- **Compare** HCs (`How is #induction different from #deduction?`)
- **Suggest** HCs for a situation (`Which HCs fit a debate about rent control?`)
- **Say so** when the HC descriptions don't cover a question, then give a clearly labelled general answer

## How it works

The corpus is small (76 docs, ~3k tokens each), so most questions are a routing problem: *which HC is this
about?* The agent gets a one-line-per-HC catalog in its system prompt, reads the whole docs it picks with a
sandboxed `read_file` tool, and finishes with a structured `final_answer` (status, source label, answer,
cited HCs, links). The code checks that every cited HC was actually read.

No vector DB, no agent framework: a plain Python loop over the OpenAI Responses API. Domain knowledge lives
in `skills/hcs/SKILL.md`, so new domains can be added as new skill folders.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
cp .env.example .env   # then add your OPENAI_API_KEY
```

**The HC description docs are not included.** They are Minerva's content (from the student portal), so this
repo ships only the code, prompts, and evals. Put one Markdown file per HC in `data/hcs/docs/<hc>.md`, each with
a `# #<hc> | ...` title, a `> Source: [<url>](<url>)` line, a `## <one-line definition>` heading, and a
`Habit of Mind | ...` or `Foundational Concept | ...` type line. Then build the catalog:

```sh
uv run python scripts/build_catalog.py
```

## Usage

```sh
uv run hc ask "What does #evidencebased mean?"          # add --trace to see tool calls and tokens
uv run hc eval --cases evals/questions.dev.jsonl        # add --out evals/runs/<name>.jsonl to save rows
```

### Slack bot

Replies in threads to @-mentions and DMs, and uses earlier thread replies as context. It runs in Socket
Mode, so it needs no public URL.

```sh
uv run hc slack --dry-run   # check config with fake events, no network
uv run hc slack
```

Fill in `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `.env`. One-time app setup at api.slack.com/apps:
enable Socket Mode; create an app-level token with `connections:write` (`SLACK_APP_TOKEN`); add bot scopes
`app_mentions:read`, `chat:write`, `reactions:write`, `im:history`, `channels:history`, `groups:history`;
subscribe to events `app_mention` and `message.im`; turn on the App Home Messages tab; install to the
workspace (`SLACK_BOT_TOKEN`).

## Current eval

Routing recall (all `required_hcs` read) and status match; no answer-quality judge yet. Model `gpt-5.6-sol`.

| Cases | Status match | Routing recall | Mean tokens | Mean steps | Mean latency |
|---|---|---|---|---|---|
| dev (13) | 13/13 | 11/11 | ~8.7k | 1.8 | ~7 s |
| answers (7) | 6–7/7 (answer-007 flaky) | 5/5 | ~5.9k | 1.7 | ~6 s |

## Project layout

```
data/hcs/docs/        HC description docs, not in git (+ generated catalog.md / catalog.jsonl)
skills/hcs/SKILL.md   how the agent should use the HC catalog
prompts/base.md       domain-agnostic base rules
src/minerva_hc/       agent loop, tools, LLM client, CLI, evals, Slack adapter
evals/                dev / holdout / answers question sets
```

## Development

```sh
uv run pytest && uv run ruff check     # fake LLM, no API calls; data tests skip without the docs
uv run python scripts/build_catalog.py # rebuild the catalog after editing docs
```

## License

MIT for the code. The HC descriptions belong to Minerva University and are not covered.
