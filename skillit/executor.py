from __future__ import annotations

import re
from pathlib import Path

from .compressor import build_context
from .config import RuntimeConfig
from .llm import BaseLLM, OpenAIResponsesLLM
from .memory import MemoryExtractor, compact_memories
from .planner import Planner
from .schema import Skill, Turn, utc_now
from .session_store import SessionStore
from .skill_loader import load_skills
from .tools import ToolRegistry


class SkillRouter:
    def route(self, user_input: str, skills: list[Skill]) -> Skill:
        text = user_input.lower()
        best = None
        best_score = -1
        for s in skills:
            score = 0
            for trig in s.triggers:
                if trig and trig in text:
                    score += 1
            if score > best_score:
                best_score = score
                best = s
        return best or Skill(
            id="default",
            name="default",
            description="fallback skill",
            triggers=[],
            body="You are a concise assistant. Follow plan first, then answer directly.",
            path="inline://default",
            root_dir="",
            scripts=[],
        )


class AgentExecutor:
    def __init__(self, cfg: RuntimeConfig | None = None, llm: BaseLLM | None = None) -> None:
        self.cfg = cfg or RuntimeConfig()
        self.skills = load_skills(Path(self.cfg.skills_dir))
        self.soul_prompt = self._load_soul(Path(self.cfg.soul_file))
        self.skill_script_index = self._build_skill_script_index(self.skills)
        self.router = SkillRouter()
        self.sessions = SessionStore(Path(self.cfg.sessions_dir))
        self.extractor = MemoryExtractor()
        self.planner = Planner()
        self.tools = ToolRegistry(workspace_root=Path.cwd(), script_index=self.skill_script_index)
        self.llm = llm or OpenAIResponsesLLM()

    def list_skills(self) -> list[str]:
        out = []
        for s in self.skills:
            out.append(f"{s.name}#{s.id} ({','.join(s.triggers)}) scripts={len(s.scripts)}")
        return out

    def list_tools(self) -> list[dict]:
        return self.tools.list_tools()

    def create_session(self, title: str = "session") -> str:
        return self.sessions.create(title=title)

    def list_sessions(self) -> list[dict]:
        return self.sessions.list_sessions()

    def run_turn(self, user_input: str, session_id: str | None = None) -> dict:
        sid = self.sessions.ensure(session_id)
        skill = self.router.route(user_input, self.skills)

        recent_turns = self.sessions.load_recent_turns(sid, n=self.cfg.short_term_turns)
        memories = self.sessions.load_memories(sid, max_items=self.cfg.max_memory_items)
        mem_summary = compact_memories(memories)

        plan = self.planner.build_plan(user_input=user_input, history=recent_turns)
        self.sessions.append_plan(sid, plan)

        tool_results = []
        step_result_map: dict[str, dict] = {}
        for step in plan.steps:
            if step.kind != "tool":
                continue
            resolved_input = self._resolve_tool_input(step.tool_input, step_result_map)
            result = self.tools.run(step.tool, resolved_input)
            payload = {
                "ts": utc_now(),
                "step_id": step.id,
                "depends_on": step.depends_on,
                "tool": step.tool,
                "planned_input": step.tool_input,
                "input": resolved_input,
                "result": result,
            }
            tool_results.append(payload)
            step_result_map[step.id] = payload
            self.sessions.append_tool_result(sid, payload)

        tool_summary = self._render_tool_summary(tool_results)
        plan_summary = self._render_plan(plan)

        history_for_prompt = recent_turns + [Turn(role="user", content=user_input)]
        context = build_context(
            user_input=user_input,
            short_term=history_for_prompt,
            memory_summary=mem_summary,
            soul_prompt=self.soul_prompt,
            skill_prompt=skill.body,
            plan_summary=plan_summary,
            tool_summary=tool_summary,
            max_chars=self.cfg.max_context_chars,
        )
        reply = self.llm.generate(context).text

        self.sessions.append_turn(sid, Turn(role="user", content=user_input))
        self.sessions.append_turn(sid, Turn(role="assistant", content=reply))

        for item in self.extractor.extract(user_input):
            self.sessions.append_memory(sid, item)
        for item in self.extractor.extract(reply):
            self.sessions.append_memory(sid, item)

        return {
            "session_id": sid,
            "skill": skill.name,
            "plan": plan.to_json(),
            "tool_results": tool_results,
            "reply": reply,
        }

    def _render_plan(self, plan) -> str:
        rows = [f"goal: {plan.goal}"]
        for s in plan.steps:
            if s.kind == "tool":
                dep = f" depends_on={s.depends_on}" if s.depends_on else ""
                rows.append(f"- {s.id} [{s.kind}] {s.tool}{dep} input={s.tool_input}")
            else:
                rows.append(f"- {s.id} [{s.kind}] {s.description}")
        return "\n".join(rows)

    def _resolve_tool_input(self, payload: dict, step_results: dict[str, dict]) -> dict:
        def resolve_value(v):
            if isinstance(v, dict):
                return {k: resolve_value(val) for k, val in v.items()}
            if isinstance(v, list):
                return [resolve_value(x) for x in v]
            if not isinstance(v, str):
                return v

            # quick alias for common chain: read first search hit file
            if v == "{{last_search_hit_file}}":
                for key in sorted(step_results.keys(), reverse=True):
                    rec = step_results[key]
                    if rec.get("tool") != "search_text":
                        continue
                    hits = (((rec.get("result") or {}).get("data") or {}).get("hits") or [])
                    if hits:
                        return hits[0].get("file", "")
                return ""

            # generic placeholder: {{s2.result.data.hits.0.file}}
            m = re.fullmatch(r"\{\{([^}]+)\}\}", v.strip())
            if not m:
                return v
            path = m.group(1).strip().split(".")
            if not path:
                return v
            root = step_results.get(path[0], {})
            cur = root
            for part in path[1:]:
                if isinstance(cur, list):
                    if not part.isdigit():
                        return ""
                    idx = int(part)
                    if idx < 0 or idx >= len(cur):
                        return ""
                    cur = cur[idx]
                    continue
                if not isinstance(cur, dict):
                    return ""
                cur = cur.get(part)
                if cur is None:
                    return ""
            return cur

        return resolve_value(payload)

    def _render_tool_summary(self, tool_results: list[dict]) -> str:
        if not tool_results:
            return "(no tool called)"
        rows = []
        total = 0
        for rec in tool_results:
            line = f"[{rec['step_id']}] {rec['tool']} => {rec['result']}"
            if total + len(line) > self.cfg.max_tool_output_chars:
                break
            rows.append(line)
            total += len(line)
        return "\n".join(rows)

    @staticmethod
    def _load_soul(path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @staticmethod
    def _build_skill_script_index(skills: list[Skill]) -> dict[str, dict[str, str]]:
        idx: dict[str, dict[str, str]] = {}
        for s in skills:
            sid = (s.id or s.name).lower()
            scripts: dict[str, str] = {}
            for p in s.scripts:
                script_name = Path(p).name
                scripts[script_name] = p
            idx[sid] = scripts
        return idx
