import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data/hcs/docs"
CATALOG = ROOT / "data/hcs/catalog.jsonl"
CATALOG_MD = ROOT / "data/hcs/catalog.md"
SKILL = ROOT / "skills/hcs/SKILL.md"

pytestmark = pytest.mark.docs

# Upstream doc has an empty Categorization section.
NO_TYPE = {"ethicaljudgment"}


def load():
    return [json.loads(line) for line in CATALOG.read_text().splitlines()]


def test_catalog_matches_docs():
    entries = load()
    assert len(entries) == 76
    assert {e["hc"] for e in entries} == {p.stem for p in DOCS.glob("*.md")}


def test_catalog_fields():
    for e in load():
        for field in ("hc", "url", "definition", "path"):
            assert e[field], f"{e['hc']}: missing {field}"
        assert (ROOT / e["path"]).exists()
        assert e["type"] in {"Habit of Mind", "Foundational Concept", None}
        assert (e["type"] is None) == (e["hc"] in NO_TYPE), e["hc"]


def test_catalog_md_one_line_per_hc():
    names = {e["hc"] for e in load()}
    lines = [line for line in CATALOG_MD.read_text().splitlines() if line.startswith("- ")]
    assert len(lines) == 76
    assert {re.match(r"- (\S+) \(", line).group(1) for line in lines} == names


def test_skill_paths_exist():
    front = SKILL.read_text().split("---")[1]
    for key in ("catalog", "docs"):
        value = re.search(rf"^{key}: (\S+)$", front, re.MULTILINE).group(1)
        assert (ROOT / value).exists(), value
