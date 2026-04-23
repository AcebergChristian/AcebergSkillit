from __future__ import annotations

import re

from .schema import MemoryItem


class MemoryExtractor:
    """Rule-based extractor. Deterministic and tiny."""

    pref_re = re.compile(r"\b(i prefer|my preference|喜欢|偏好)\b", re.I)
    task_re = re.compile(r"\b(todo|task|next|待办|下一步|需要|必须)\b", re.I)

    def extract(self, text: str) -> list[MemoryItem]:
        out: list[MemoryItem] = []
        clean = text.strip().replace("\n", " ")
        if len(clean) < 8:
            return out

        low = clean.lower()
        if self.pref_re.search(low):
            out.append(MemoryItem(kind="preference", content=clean, score=0.85))
        if self.task_re.search(low):
            out.append(MemoryItem(kind="task", content=clean, score=0.75))
        if not out and len(clean) <= 220:
            out.append(MemoryItem(kind="fact", content=clean, score=0.55))
        return out


def compact_memories(items: list[MemoryItem], max_chars: int = 1800) -> str:
    if not items:
        return ""
    ranked = sorted(items, key=lambda x: (x.score, x.ts), reverse=True)
    rows: list[str] = []
    total = 0
    for it in ranked:
        row = f"[{it.kind}] {it.content}"
        if total + len(row) > max_chars:
            continue
        rows.append(row)
        total += len(row)
    return "\n".join(rows)
