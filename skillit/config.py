from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RuntimeConfig:
    skills_dir: Path = Path("skills")
    sessions_dir: Path = Path("sessions")
    soul_file: Path = Path("soul.md")
    short_term_turns: int = 8
    max_context_chars: int = 7000
    max_memory_items: int = 2000
    max_tool_output_chars: int = 2000
