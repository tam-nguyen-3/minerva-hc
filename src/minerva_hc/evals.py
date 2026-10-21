"""Eval harness: routing recall + status match from the agent trace. No judge yet."""

import json
from pathlib import Path

from minerva_hc import agent

STATUS_MAP = {
    "answer": "answer",
    "partial_answer": "partial",
    "abstain": "out_of_scope",
    "clarify": "clarify",
}


def load_cases(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def score(case: dict, result: agent.Result) -> dict:
    read = {t["name"] for t in result.trace if t.get("tool") == "read_file" and t["ok"]}
    required = set(case.get("required_hcs") or [])
    return {
        "id": case["id"],
        "category": case.get("category", ""),
        "expected": case["expected_behavior"],
        "status": result.status,
        "status_ok": result.status == STATUS_MAP[case["expected_behavior"]],
        "routing": required <= read if required else None,
        "missing": sorted(required - read),
        "extra": sorted(read - required),
        "source_label": result.source_label,
        "steps": result.steps,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "seconds": result.seconds,
        "answer": result.answer,
        "reason": result.reason,
        "trace": result.trace,
    }


def run_cases(cases: list[dict], run=agent.run) -> list[dict]:
    rows = []
    for case in cases:
        base = {"id": case["id"], "category": case.get("category", ""),
                "expected": case["expected_behavior"]}
        try:
            rows.append(score(case, run(case["question"], history=case.get("history"))))
        except Exception as e:  # noqa: BLE001 — one bad case shouldn't kill the run
            rows.append({**base, "error": f"{type(e).__name__}: {e}"})
    return rows


def _mark(v) -> str:
    return "n/a" if v is None else ("✓" if v else "✗")


def format_table(rows: list[dict]) -> str:
    lines = [
        "| id | category | expected | got | status | routing | missing | extra | steps | tokens | s |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['id']} | {r['category']} | {r['expected']} | {r['error']} |"
                         " | | | | | | |")
            continue
        lines.append(
            f"| {r['id']} | {r['category']} | {r['expected']} | {r['status']} | "
            f"{_mark(r['status_ok'])} | {_mark(r['routing'])} | {' '.join(r['missing'])} | "
            f"{' '.join(r['extra'])} | {r['steps']} | {r['tokens_in'] + r['tokens_out']:,} | "
            f"{r['seconds']} |"
        )
    done = [r for r in rows if "status" in r]
    routed = [r for r in done if r["routing"] is not None]
    lines.append("")
    if not done:
        lines.append(f"no cases ran ({len(rows)} errored)")
        return "\n".join(lines)
    tokens = [r["tokens_in"] + r["tokens_out"] for r in done]
    secs = [r["seconds"] for r in done]
    lines.append(
        f"status match {sum(r['status_ok'] for r in done)}/{len(done)} · "
        f"routing recall {sum(r['routing'] for r in routed)}/{len(routed)} · "
        f"tokens mean {sum(tokens) // len(done):,} total {sum(tokens):,} · "
        f"steps mean {sum(r['steps'] for r in done) / len(done):.1f} · "
        f"latency mean {sum(secs) / len(done):.1f}s max {max(secs):.1f}s"
        + (f" · errored {len(rows) - len(done)}" if len(rows) > len(done) else "")
    )
    return "\n".join(lines)
