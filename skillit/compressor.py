from __future__ import annotations

from .schema import Turn


def _render_turns(turns: list[Turn]) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in turns)


def _compress_old_turns(turns: list[Turn], keep_last: int = 4) -> str:
    if len(turns) <= keep_last:
        return _render_turns(turns)
    old = turns[:-keep_last]
    recent = turns[-keep_last:]
    old_summary = " | ".join(t.content[:60].replace("\n", " ") for t in old)
    return f"summary(old): {old_summary}\n" + _render_turns(recent)


def build_context(
    *,
    user_input: str,
    short_term: list[Turn],
    memory_summary: str,
    soul_prompt: str,
    skill_prompt: str,
    plan_summary: str,
    tool_summary: str,
    max_chars: int = 7000,
) -> str:
    parts = [
        "# Soul\n" + (soul_prompt.strip() or "(empty)"),
        "# System Skill\n" + skill_prompt.strip(),
        "# Plan (Must Follow)\n" + plan_summary.strip(),
        "# Tool Results\n" + (tool_summary or "(empty)"),
        "# Retrieved Memory\n" + (memory_summary or "(empty)"),
        "# Conversation\n" + _compress_old_turns(short_term),
        "# New User Input\n" + user_input.strip(),
    ]
    raw = "\n\n".join(parts)
    if len(raw) <= max_chars:
        return raw

    mem_cut = memory_summary[: max_chars // 5]
    tool_cut = tool_summary[: max_chars // 4]
    conv_cut = _compress_old_turns(short_term[-4:], keep_last=4)
    final = "\n\n".join(
        [
            "# Soul\n" + (soul_prompt.strip() or "(empty)"),
            "# System Skill\n" + skill_prompt.strip(),
            "# Plan (Must Follow)\n" + plan_summary.strip(),
            "# Tool Results\n" + tool_cut,
            "# Retrieved Memory\n" + mem_cut,
            "# Conversation\n" + conv_cut,
            "# New User Input\n" + user_input.strip(),
        ]
    )
    return final[:max_chars]
