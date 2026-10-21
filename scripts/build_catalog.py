"""Build data/hcs/catalog.{jsonl,md} from the HC description docs. Deterministic, no LLM."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data/hcs/docs"
OUT = ROOT / "data/hcs"

TYPES = {
    "Habit of Mind": "Habit of Mind",
    "Habit": "Habit of Mind",
    "Foundational Concept": "Foundational Concept",
    "Foundation Concept": "Foundational Concept",
}
TYPE_TAGS = {"Habit of Mind": "HoM", "Foundational Concept": "FC"}
TYPE_LINE = re.compile(
    r"^(" + "|".join(sorted(TYPES, key=len, reverse=True)) + r")\s*\|(.*)$", re.MULTILINE
)
REQUIRED = ("hc", "url", "definition")
OPTIONAL = ("type", "category", "classes", "unit")


def first(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).replace("\u00ad", "").strip() if m else None


def normalize_class(name: str) -> str:
    name = re.sub(r"\bAnalysis\b", "Analyses", name)
    return re.sub(r"\bCommunication\b", "Communications", name)


def parse_class(raw: str | None) -> tuple[list[str], list[str]]:
    if not raw:
        return [], []
    semesters = list(dict.fromkeys(re.findall(r"Semester \w+", raw)))
    rest = re.sub(r"\(?Semester \w+\)?", "", raw)
    classes = [normalize_class(c.strip()) for c in re.split(r"[|&]", rest) if c.strip()]
    return classes, semesters


def parse_doc(path: Path) -> dict:
    text = path.read_text()
    hc = path.stem
    tag = first(r"^# #(\S+) \| Minerva University", text)
    if tag != hc:
        print(f"warning: {path.name}: H1 tag is {tag!r}", file=sys.stderr)
    type_match = TYPE_LINE.search(text)
    class_raw = first(r"^\*\*Class:\*\*(.*)$", text)
    classes, semesters = parse_class(class_raw)
    return {
        "hc": hc,
        "definition": first(r"^## (.+)$", text),
        "type": TYPES[type_match.group(1)] if type_match else None,
        "category": (
            [c.strip() for c in type_match.group(2).split("|") if c.strip()] if type_match else []
        ),
        "classes": classes,
        "semesters": semesters,
        "class_raw": class_raw,
        "unit": first(r"^\*\*Unit:\*\*(.*)$", text),
        "url": first(r"^> Source: \[([^\]]+)\]", text),
        "path": str(path.relative_to(ROOT)),
        "word_count": len(text.split()),
    }


def render_md(entries: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for e in entries:
        groups.setdefault(e["classes"][0] if e["classes"] else "Other", []).append(e)
    lines = [
        "# HC catalog",
        "",
        (
            "One line per HC: `name (HoM|FC): definition`. HoM = Habit of Mind,"
            " FC = Foundational Concept. Pass `name` to read_file."
        ),
    ]
    for cls in sorted(groups):
        lines += ["", f"## {cls}"]
        for e in groups[cls]:
            lines.append(f"- {e['hc']} ({TYPE_TAGS.get(e['type'], '?')}): {e['definition']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    entries = [parse_doc(p) for p in sorted(DOCS.glob("*.md"))]
    (OUT / "catalog.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries))
    (OUT / "catalog.md").write_text(render_md(entries))
    print(f"{len(entries)} HCs -> {OUT.relative_to(ROOT)}/catalog.{{jsonl,md}}")
    failed = False
    for e in entries:
        missing = [f for f in REQUIRED + OPTIONAL if not e[f]]
        if missing:
            print(f"missing: {e['hc']}: {', '.join(missing)}")
            failed |= any(f in REQUIRED for f in missing)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
