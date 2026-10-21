"""Tools exposed to the model. Sandboxed to data/ and skills/."""

import difflib
import re

from minerva_hc.skills import ROOT, load_skills

ALLOWED = [ROOT / "data", ROOT / "skills"]
MAX_CHARS = 40_000
NAME = re.compile(r"^[a-z0-9_-]+$")


def doc_dirs():
    return [(ROOT / s["docs"]).resolve() for s in load_skills() if s.get("docs")]


def normalize(name: str) -> str:
    return name.strip().lstrip("#").lower()


def read_file(name: str) -> tuple[bool, str]:
    name = normalize(name)
    if not NAME.match(name):
        return False, f"error: invalid name {name!r}; use a name from the catalog"
    for d in doc_dirs():
        path = (d / f"{name}.md").resolve()
        if not any(path.is_relative_to(a) for a in ALLOWED):
            continue
        if path.is_file():
            text = path.read_text()
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS] + f"\n\n[truncated at {MAX_CHARS} chars]"
            return True, text
    known = [p.stem for d in doc_dirs() for p in d.glob("*.md")]
    close = difflib.get_close_matches(name, known, n=5, cutoff=0.5)
    return False, f"error: no document named {name!r}. Close matches: {', '.join(close) or 'none'}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Return the full text of a document by its catalog name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "e.g. evidencebased"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "Give the final answer. Always end with this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["answer", "partial", "out_of_scope", "clarify"]},
                    "source_label": {"type": "string", "enum": ["hc_description", "general"]},
                    "answer": {"type": "string"},
                    "cited": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of documents read and used.",
                    },
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "reason": {
                        "type": "string",
                        "description": "Why the answer is partial, out of scope, or needs clarifying.",
                    },
                },
                "required": ["status", "source_label", "answer", "cited", "urls"],
            },
        },
    },
]
