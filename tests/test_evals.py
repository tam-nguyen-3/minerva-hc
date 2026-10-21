import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data/hcs/docs"


@pytest.mark.docs
def test_eval_references_exist():
    for path in sorted((ROOT / "evals").glob("*.jsonl")):
        for line in path.read_text().splitlines():
            case = json.loads(line)
            for hc in case.get("required_hcs", []):
                assert (DOCS / f"{hc}.md").exists(), f"{case['id']}: no doc for {hc}"
            for ev in case.get("gold_evidence", []):
                assert (ROOT / ev["file"]).exists(), f"{case['id']}: {ev['file']}"


from minerva_hc.agent import Result
from minerva_hc.evals import format_table, run_cases, score


def result(status="answer", reads=(), failed=()):
    trace = [{"tool": "read_file", "name": n, "ok": True, "chars": 1} for n in reads]
    trace += [{"tool": "read_file", "name": n, "ok": False, "chars": 1} for n in failed]
    return Result(status=status, source_label="hc_description", answer="A.", trace=trace,
                  steps=2, tokens_in=100, tokens_out=10, seconds=1.0)


def case(expected="answer", required=("evidencebased",), **kw):
    return {"id": "c1", "category": "x", "question": "q", "expected_behavior": expected,
            "required_hcs": list(required), **kw}


def test_score_routing_hit_with_extra_reads():
    r = score(case(), result(reads=["evidencebased", "sourcequality"]))
    assert r["routing"] is True and r["status_ok"] is True
    assert r["missing"] == [] and r["extra"] == ["sourcequality"]


def test_score_failed_read_is_a_miss():
    r = score(case(), result(failed=["evidencebased"]))
    assert r["routing"] is False and r["missing"] == ["evidencebased"]


def test_score_no_required_is_na_and_status_mapping():
    assert score(case("abstain", ()), result("out_of_scope"))["routing"] is None
    assert score(case("partial_answer"), result("partial"))["status_ok"] is True
    assert score(case("clarify", ()), result("partial"))["status_ok"] is False


def test_run_cases_passes_history_and_records_errors():
    seen = []

    def fake_run(q, history=None):
        seen.append(history)
        if q == "boom":
            raise RuntimeError("x")
        return result(reads=["evidencebased"])

    hist = [{"role": "user", "content": "hi"}]
    cases = [case(), case(history=hist), {**case(), "id": "c3", "question": "boom"}]
    rows = run_cases(cases, run=fake_run)
    assert seen == [None, hist, None]
    assert rows[0]["status_ok"] and rows[1]["status_ok"]
    assert rows[2]["error"] == "RuntimeError: x"
    table = format_table(rows)
    assert "status match 2/2" in table and "routing recall 2/2" in table
    assert "errored 1" in table
