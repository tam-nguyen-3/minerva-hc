import pytest

from minerva_hc.skills import ROOT, load_skills, system_prompt


def test_load_skills():
    (hcs,) = load_skills()
    assert hcs["name"] == "hcs"
    assert hcs["catalog"] == "data/hcs/catalog.md"
    assert hcs["docs"] == "data/hcs/docs"
    assert "explaining, comparing" in hcs["description"]


@pytest.mark.docs
def test_system_prompt_has_everything():
    prompt = system_prompt()
    assert "final_answer" in prompt
    assert "## Skill: hcs" in prompt
    catalog = (ROOT / "data/hcs/catalog.md").read_text()
    entries = [line for line in catalog.splitlines() if line.startswith("- ")]
    assert len(entries) == 76
    assert all(line in prompt for line in entries)
