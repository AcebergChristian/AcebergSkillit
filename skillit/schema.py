from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(slots=True)
class Turn:
    role: str
    content: str
    ts: str = field(default_factory=utc_now)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Turn":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            ts=data.get("ts", utc_now()),
        )


@dataclass(slots=True)
class MemoryItem:
    kind: str  # fact | preference | task | summary
    content: str
    source: str = "runtime"
    score: float = 0.5
    ts: str = field(default_factory=utc_now)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "MemoryItem":
        return cls(
            kind=data.get("kind", "fact"),
            content=data.get("content", ""),
            source=data.get("source", "runtime"),
            score=float(data.get("score", 0.5)),
            ts=data.get("ts", utc_now()),
        )


@dataclass(slots=True)
class Skill:
    id: str
    name: str
    description: str
    triggers: list[str]
    body: str
    path: str
    root_dir: str = ""
    scripts: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowTask:
    id: str
    kind: str  # understand | research | collect | transform | export | codegen | execute | respond
    description: str
    skill_id: str = ""
    input_hint: str = ""
    output_hint: str = ""
    status: str = "pending"
    depends_on: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorkflowPlan:
    goal: str
    tasks: list[WorkflowTask]
    primary_skill_id: str = ""
    ts: str = field(default_factory=utc_now)

    def to_json(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "primary_skill_id": self.primary_skill_id,
            "tasks": [t.to_json() for t in self.tasks],
            "ts": self.ts,
        }


@dataclass(slots=True)
class PlanStep:
    id: str
    kind: str  # analyze | tool | respond
    description: str
    tool: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Plan:
    goal: str
    steps: list[PlanStep]
    ts: str = field(default_factory=utc_now)

    def to_json(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_json() for s in self.steps],
            "ts": self.ts,
        }
