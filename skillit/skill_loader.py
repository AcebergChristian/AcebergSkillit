from __future__ import annotations

from pathlib import Path

from .schema import Skill


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw_head = text[4:end].splitlines()
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in raw_head:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, body


def _csv(value: str) -> list[str]:
    return [x.strip().lower() for x in value.split(",") if x.strip()]


def load_skills(skills_dir: Path) -> list[Skill]:
    skills: list[Skill] = []
    if not skills_dir.exists():
        return skills

    for path in sorted(skills_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = _split_front_matter(text)
        name = meta.get("name", path.stem)
        description = meta.get("description", "")
        triggers = _csv(meta.get("triggers", ""))
        skills.append(
            Skill(
                name=name,
                description=description,
                triggers=triggers,
                body=body.strip(),
                path=str(path),
            )
        )
    return skills
