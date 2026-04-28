from __future__ import annotations

from pathlib import Path

from .schema import Skill

SCRIPT_EXTS = {".py", ".sh", ".js"}
ENTRY_FILES = ("SKILL.md", "skill.md")


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


def _collect_scripts(skill_dir: Path) -> list[str]:
    return _collect_paths(skill_dir / "scripts", allow_exts=SCRIPT_EXTS)


def _collect_paths(base_dir: Path, allow_exts: set[str] | None = None) -> list[str]:
    if not base_dir.exists():
        return []
    out = []
    for p in sorted(base_dir.rglob("*")):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.relative_to(base_dir).parts):
            continue
        if allow_exts is not None and p.suffix.lower() not in allow_exts:
            continue
        out.append(str(p))
    return out


def _resolve_entry_file(skill_dir: Path) -> Path | None:
    for name in ENTRY_FILES:
        candidate = skill_dir / name
        if candidate.exists():
            return candidate
    return None


def _load_skill_pack(skill_dir: Path) -> Skill | None:
    md = _resolve_entry_file(skill_dir)
    if md is None:
        return None

    text = md.read_text(encoding="utf-8")
    meta, body = _split_front_matter(text)
    skill_id = meta.get("id", skill_dir.name)
    name = meta.get("name", skill_dir.name)
    description = meta.get("description", "")
    triggers = _csv(meta.get("triggers", ""))
    scripts = _collect_scripts(skill_dir)
    references = _collect_paths(skill_dir / "references")
    assets = _collect_paths(skill_dir / "assets")

    return Skill(
        id=skill_id,
        name=name,
        description=description,
        triggers=triggers,
        body=body.strip(),
        path=str(md),
        root_dir=str(skill_dir),
        scripts=scripts,
        references=references,
        assets=assets,
    )


def _load_legacy_md(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    meta, body = _split_front_matter(text)
    skill_id = meta.get("id", path.stem)
    name = meta.get("name", path.stem)
    description = meta.get("description", "")
    triggers = _csv(meta.get("triggers", ""))
    return Skill(
        id=skill_id,
        name=name,
        description=description,
        triggers=triggers,
        body=body.strip(),
        path=str(path),
        root_dir=str(path.parent),
        scripts=[],
        references=[],
        assets=[],
    )


def load_skills(skills_dir: Path) -> list[Skill]:
    skills: list[Skill] = []
    if not skills_dir.exists():
        return skills

    # Preferred: skills/<skill_name>/SKILL.md (+ scripts/ references/ assets/)
    for p in sorted(skills_dir.iterdir()):
        if not p.is_dir():
            continue
        skill = _load_skill_pack(p)
        if skill:
            skills.append(skill)

    # Backward-compatible: skills/*.md
    for path in sorted(skills_dir.glob("*.md")):
        skills.append(_load_legacy_md(path))

    return skills
