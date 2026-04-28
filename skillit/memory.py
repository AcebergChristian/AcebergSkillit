from __future__ import annotations

import re

from .schema import MemoryItem


class MemoryExtractor:
    """Rule-based extractor. Deterministic and tiny."""

    pref_re = re.compile(r"\b(i prefer|my preference|喜欢|偏好)\b", re.I)
    task_re = re.compile(r"\b(todo|task|next|待办|下一步|需要|必须)\b", re.I)
    constraint_re = re.compile(r"\b(存到|输出到|导出|excel|xlsx|csv|目录|文件夹|today|今天|最新)\b", re.I)

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
        if self.constraint_re.search(low):
            out.append(MemoryItem(kind="summary", content=clean, score=0.8))
        if not out and len(clean) <= 220:
            out.append(MemoryItem(kind="fact", content=clean, score=0.55))
        return out


def compact_memories(items: list[MemoryItem], max_chars: int = 1800) -> str:
    if not items:
        return ""
    ranked = sorted(items, key=lambda x: (x.score, x.ts), reverse=True)
    rows: list[str] = []
    total = 0
    seen: set[tuple[str, str]] = set()
    for it in ranked:
        row = f"[{it.kind}] {it.content}"
        key = (it.kind, it.content)
        if key in seen:
            continue
        if total + len(row) > max_chars:
            continue
        rows.append(row)
        total += len(row)
        seen.add(key)
    return "\n".join(rows)
