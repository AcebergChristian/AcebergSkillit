from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from skillit.executor import AgentExecutor


router = APIRouter(prefix="/api")
agent = AgentExecutor()


class RunRequest(BaseModel):
    requirement: str
    title: str = "web-console"
    session_id: str | None = None
    reuse_session_by_title: bool = True


def _session_status(snapshot: dict) -> str:
    events = snapshot.get("events") or []
    tools = snapshot.get("tool_results") or []
    if not events and not tools:
        return "idle"
    for item in reversed(tools):
        if item.get("tool") != "run_local_script":
            continue
        data = ((item.get("result") or {}).get("data") or {})
        return "completed" if data.get("exit_code") == 0 else "error"
    if not events:
        return "idle"
    last_type = (events[-1] or {}).get("type", "")
    if last_type in {"session", "workflow", "skill", "plan", "tool", "run", "repair"}:
        return "running"
    return "idle"


def _serialize_session_row(row: dict) -> dict:
    snapshot = agent.get_session_snapshot(row["id"], limit=80)
    turns = snapshot.get("turns") or []
    last_turn = turns[-1] if turns else {}
    return {
        **row,
        "status": _session_status(snapshot),
        "task_output_dir": snapshot.get("task_output_dir", ""),
        "output_count": len(snapshot.get("outputs") or []),
        "last_event": (snapshot.get("events") or [{}])[-1],
        "last_turn_preview": str(last_turn.get("content", "")).strip()[:120],
        "last_turn_role": last_turn.get("role", ""),
        "turns_count": len(turns),
        "workflow": snapshot.get("workflow"),
    }


@router.get("/overview")
def get_overview() -> dict:
    sessions = agent.list_sessions()
    active = sessions[0] if sessions else None
    skills = agent.skills
    latest_snapshot = agent.get_session_snapshot(active["id"], limit=50) if active else None
    return {
        "stats": {
            "active_sessions": len(sessions),
            "skills_loaded": len(skills),
            "learned_skills": len([s for s in skills if s.id.startswith("learned__")]),
            "output_files": sum(len(agent.get_session_snapshot(s["id"], limit=20).get("outputs") or []) for s in sessions[:5]),
        },
        "active_session": _serialize_session_row(active) if active else None,
        "recent_events": (latest_snapshot or {}).get("events", [])[-8:],
    }


@router.get("/runtime")
def get_runtime() -> dict:
    sessions = agent.list_sessions()
    active = sessions[0]["id"] if sessions else ""
    cwd = Path.cwd().resolve()
    return {
        "workspace_name": cwd.name,
        "workspace_path": str(cwd),
        "current_path": str(cwd),
        "active_session_id": active,
    }


@router.get("/sessions")
def list_sessions() -> dict:
    items = [_serialize_session_row(row) for row in agent.list_sessions()]
    return {"items": items}


@router.get("/sessions/{sid}")
def get_session(sid: str) -> dict:
    return agent.get_session_snapshot(sid, limit=300)


@router.get("/skills")
def list_skills() -> dict:
    return {
        "items": [
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "triggers": skill.triggers,
                "scripts": skill.scripts,
                "references": skill.references,
                "assets": skill.assets,
                "type": "learned" if skill.id.startswith("learned__") else "system",
                "status": "loaded",
                "path": skill.path,
            }
            for skill in agent.skills
        ]
    }


@router.post("/run")
def run_requirement(body: RunRequest) -> dict:
    result = agent.run_requirement(
        body.requirement,
        session_id=body.session_id,
        title=body.title,
        reuse_session_by_title=body.reuse_session_by_title,
    )
    snapshot = agent.get_session_snapshot(result["session_id"], limit=300)
    return {"result": result, "snapshot": snapshot}


@router.post("/chat")
def chat(body: RunRequest) -> dict:
    return run_requirement(body)


@router.post("/run/stream")
def run_requirement_stream(body: RunRequest) -> StreamingResponse:
    q: queue.Queue[dict | object] = queue.Queue()
    sentinel = object()

    def on_event(event: dict) -> None:
        q.put({"type": "event", "data": event})

    def worker() -> None:
        try:
            result = agent.run_requirement(
                body.requirement,
                session_id=body.session_id,
                title=body.title,
                event_callback=on_event,
                reuse_session_by_title=body.reuse_session_by_title,
            )
            snapshot = agent.get_session_snapshot(result["session_id"], limit=300)
            q.put({"type": "final", "data": {"result": result, "snapshot": snapshot}})
        except Exception as exc:  # pragma: no cover
            q.put({"type": "error", "data": {"message": str(exc)}})
        finally:
            q.put(sentinel)

    def stream():
        while True:
            item = q.get()
            if item is sentinel:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    threading.Thread(target=worker, daemon=True).start()
    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/chat/stream")
def chat_stream(body: RunRequest) -> StreamingResponse:
    return run_requirement_stream(body)
