from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .schema import MemoryItem, Plan, Turn, utc_now


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.json"
        if not self.manifest.exists():
            self.manifest.write_text(
                json.dumps({"active_session": "", "sessions": {}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def create(self, title: str = "session") -> str:
        sid = self._new_id()
        base = self.root / sid
        base.mkdir(parents=True, exist_ok=True)

        files = {
            "meta_file": str(base / "meta.json"),
            "turns_file": str(base / "turns.jsonl"),
            "memories_file": str(base / "memories.jsonl"),
            "plans_file": str(base / "plans.jsonl"),
            "tools_file": str(base / "tools.jsonl"),
        }
        meta = {"id": sid, "title": title, "created_at": utc_now(), "updated_at": utc_now()}
        Path(files["meta_file"]).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        for k in ["turns_file", "memories_file", "plans_file", "tools_file"]:
            Path(files[k]).write_text("", encoding="utf-8")

        man = self._load_manifest()
        man["sessions"][sid] = files
        man["active_session"] = sid
        self._save_manifest(man)
        return sid

    def get_or_create_by_title(self, title: str) -> str:
        man = self._load_manifest()
        sessions = man.get("sessions", {})
        matched: list[tuple[str, str]] = []
        for sid, rec in sessions.items():
            meta = self._read_json(Path(rec["meta_file"]))
            if meta.get("title") == title:
                matched.append((sid, meta.get("updated_at", "")))
        if matched:
            matched.sort(key=lambda x: x[1], reverse=True)
            sid = matched[0][0]
            man["active_session"] = sid
            self._save_manifest(man)
            return sid
        return self.create(title=title)

    def ensure(self, sid: str | None = None) -> str:
        man = self._load_manifest()
        if sid and sid in man["sessions"]:
            man["active_session"] = sid
            self._save_manifest(man)
            return sid
        active = man.get("active_session", "")
        if active and active in man["sessions"]:
            return active
        return self.create("default")

    def list_sessions(self) -> list[dict]:
        out = []
        man = self._load_manifest()
        active = man.get("active_session", "")
        for sid, rec in man.get("sessions", {}).items():
            meta = self._read_json(Path(rec["meta_file"]))
            out.append(
                {
                    "id": sid,
                    "title": meta.get("title", "session"),
                    "updated_at": meta.get("updated_at", ""),
                    "active": sid == active,
                }
            )
        return sorted(out, key=lambda x: x.get("updated_at", ""), reverse=True)

    def append_turn(self, sid: str, turn: Turn) -> None:
        rec = self._session_rec(sid)
        self._append_jsonl(Path(rec["turns_file"]), turn.to_json())
        self._touch(sid)

    def load_recent_turns(self, sid: str, n: int = 8) -> list[Turn]:
        rec = self._session_rec(sid)
        rows = self._read_jsonl(Path(rec["turns_file"]))
        return [Turn.from_json(x) for x in rows[-n:]]

    def append_memory(self, sid: str, item: MemoryItem) -> None:
        rec = self._session_rec(sid)
        self._append_jsonl(Path(rec["memories_file"]), item.to_json())

    def load_memories(self, sid: str, max_items: int = 2000) -> list[MemoryItem]:
        rec = self._session_rec(sid)
        rows = self._read_jsonl(Path(rec["memories_file"]))
        items = [MemoryItem.from_json(x) for x in rows[-max_items:]]
        return items

    def append_plan(self, sid: str, plan: Plan) -> None:
        rec = self._session_rec(sid)
        self._append_jsonl(Path(rec["plans_file"]), plan.to_json())

    def append_tool_result(self, sid: str, payload: dict) -> None:
        rec = self._session_rec(sid)
        self._append_jsonl(Path(rec["tools_file"]), payload)

    def load_recent_tool_results(self, sid: str, n: int = 40) -> list[dict]:
        rec = self._session_rec(sid)
        rows = self._read_jsonl(Path(rec["tools_file"]))
        return rows[-n:]

    def session_dir(self, sid: str) -> Path:
        rec = self._session_rec(sid)
        return Path(rec["meta_file"]).parent

    def _touch(self, sid: str) -> None:
        rec = self._session_rec(sid)
        p = Path(rec["meta_file"])
        meta = self._read_json(p)
        meta["updated_at"] = utc_now()
        p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _session_rec(self, sid: str) -> dict:
        man = self._load_manifest()
        rec = man.get("sessions", {}).get(sid)
        if not rec:
            raise ValueError(f"session not found: {sid}")
        return rec

    def _load_manifest(self) -> dict:
        return self._read_json(self.manifest)

    def _save_manifest(self, data: dict) -> None:
        self.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(p: Path) -> dict:
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _append_jsonl(p: Path, payload: dict) -> None:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_jsonl(p: Path) -> list[dict]:
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    @staticmethod
    def _new_id() -> str:
        return "s_" + uuid4().hex[:10]
