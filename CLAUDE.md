# minerva-hc
LLM agent that answers questions about Minerva HCs. See PLAN.md (Status table at the top says what's next).

## Conventions
- Keep it small. No agent/RAG frameworks, no speculative abstractions, no new deps without asking.
- Domain knowledge goes in skills/<domain>/SKILL.md, not in Python or prompts/base.md.
- The agent loop must stay domain-agnostic.
- Tools are sandboxed to data/ and skills/.
- README stays short: what it is, how to run, current eval table. No dated progress logs.
- Every change to prompts/skills: run `uv run hc eval --cases evals/questions.dev.jsonl` (and
  evals/questions.answers.jsonl) and report the delta against the baseline in PLAN.md.
- Never put eval questions or expected answers into data/, skills/, or prompts.
- Terminology: "HC description(s)", never "handbook" (only the source URLs contain it).
  Source labels are `hc_description` | `general`.
- Tests never call the API: pass a scripted fake `llm` to `agent.run` (see tests/test_agent.py).
- One step per session; update the Status table in PLAN.md when a step is done.

## Architecture
- prompts/base.md + skills/*/SKILL.md (+ the catalog it declares) → system prompt (src/minerva_hc/skills.py).
- tools.py: `read_file(name)` and the `final_answer` tool schema. agent.py: loop, trace, cited-were-read check.
- llm.py: OpenAI **Responses API** (model = `OPENAI_MODEL` in .env, currently gpt-5.6-sol). It translates the
  agent's chat-style dicts and sends reasoning items back via `_items`. Don't switch to Chat Completions:
  it rejects tools combined with reasoning on gpt-5.x, and without reasoning, routing quality drops.

## Data notes
- HC description docs live in data/hcs/docs/<hc>.md (e.g. evidencebased.md); eval `gold_evidence[].file` paths point there.
- The type line is `Habit of Mind | ...` in most docs but `Habit | ...` in some (as in the official source). Treat both as Habit of Mind.
  `utility.md` says `Foundation Concept`, which means Foundational Concept. `ethicaljudgment.md` has no type line.
- data/hcs/catalog.{md,jsonl} are generated; rerun the build script after changing docs.

## Commands
- uv run hc ask "question" --trace
- uv run hc eval --cases evals/questions.dev.jsonl [--out evals/runs/<name>.jsonl]
- uv run python scripts/build_catalog.py
- uv run pytest && uv run ruff check
