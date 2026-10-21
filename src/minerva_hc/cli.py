import argparse
import json
from pathlib import Path

from minerva_hc import agent, evals


def print_result(r: agent.Result, trace: bool) -> None:
    print(r.answer)
    print(f"\n[{r.status} · {r.source_label}]" + (f" {r.reason}" if r.reason else ""))
    for name, url in zip(r.cited, r.urls + [""] * len(r.cited)):
        print(f"  #{name.lstrip('#')} {url}")
    if trace:
        print("\ntrace:")
        for t in r.trace:
            if "tool" in t:
                status = "ok" if t["ok"] else "ERR"
                print(f"  {t['tool']} {t.get('name', '')} {status} {t.get('chars', 0):,} chars")
            else:
                print(f"  check: {t['check']} {' '.join(t.get('names', []))}")
        print(f"  steps={r.steps} tokens={r.tokens_in:,}/{r.tokens_out:,} time={r.seconds}s")


def main() -> None:
    parser = argparse.ArgumentParser(prog="hc")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask", help="answer a question")
    ask.add_argument("question")
    ask.add_argument("--trace", action="store_true")
    ev = sub.add_parser("eval", help="run eval cases (routing recall + status match)")
    ev.add_argument("--cases", required=True)
    ev.add_argument("--out", help="write one JSON row per case (answer, reason, trace)")
    sl = sub.add_parser("slack", help="run the Slack bot (Socket Mode)")
    sl.add_argument("--dry-run", action="store_true", help="check config with fake events, no network")
    args = parser.parse_args()
    if args.cmd == "ask":
        print_result(agent.run(args.question), args.trace)
    elif args.cmd == "eval":
        rows = evals.run_cases(evals.load_cases(args.cases))
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text("".join(json.dumps(r) + "\n" for r in rows))
        print(evals.format_table(rows))
    elif args.cmd == "slack":
        from minerva_hc import slack

        if args.dry_run:
            raise SystemExit(0 if slack.dry_run() else 1)
        slack.serve()
