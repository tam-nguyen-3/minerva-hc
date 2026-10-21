"""Load skills/*/SKILL.md and build the system prompt. Knows nothing about any domain."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
BASE_PROMPT = ROOT / "prompts/base.md"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Tiny `key: value` parser; indented lines continue the previous value."""
    _, front, body = text.split("---", 2)
    meta: dict[str, str] = {}
    key = None
    for line in front.strip().splitlines():
        if line.startswith((" ", "\t")) and key:
            meta[key] += " " + line.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            meta[key] = value.strip()
    return meta, body.strip()


def load_skills() -> list[dict]:
    skills = []
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        meta, body = parse_frontmatter(path.read_text())
        skills.append({**meta, "body": body})
    return skills


def system_prompt() -> str:
    parts = [BASE_PROMPT.read_text().strip()]
    for skill in load_skills():
        parts.append(
            f"## Skill: {skill['name']}\n{skill.get('description', '')}\n\n{skill['body']}"
        )
        if skill.get("catalog"):
            parts.append((ROOT / skill["catalog"]).read_text().strip())
    return "\n\n".join(parts)
