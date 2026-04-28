from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .compressor import build_context
from .config import RuntimeConfig, load_dotenv
from .llm import BaseLLM, OpenAIResponsesLLM
from .memory import MemoryExtractor, compact_memories
from .planner import Planner
from .schema import Skill, Turn, WorkflowPlan, utc_now
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
            references=[],
            assets=[],
        )


class AgentExecutor:
    def __init__(self, cfg: RuntimeConfig | None = None, llm: BaseLLM | None = None) -> None:
        load_dotenv()
        self.cfg = cfg or RuntimeConfig()
        self.cfg.output_dir.mkdir(parents=True, exist_ok=True)
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
            out.append(
                f"{s.name}#{s.id} ({','.join(s.triggers)}) "
                f"scripts={len(s.scripts)} refs={len(s.references)} assets={len(s.assets)}"
            )
        return out

    def list_tools(self) -> list[dict]:
        return self.tools.list_tools()

    def create_session(self, title: str = "session") -> str:
        return self.sessions.create(title=title)

    def list_sessions(self) -> list[dict]:
        return self.sessions.list_sessions()

    # 运行一次对话
    def run_turn(self, user_input: str, session_id: str | None = None, event_callback: Callable[[dict], None] | None = None) -> dict:
        sid = self.sessions.ensure(session_id)
        task_dir = self.create_task_output_dir(sid)
        self._emit(event_callback, {"type": "session", "session_id": sid, "message": f"start session={sid}"})
        self._emit(event_callback, {"type": "task_dir", "session_id": sid, "task_dir": str(task_dir)})
        recent_turns = self.sessions.load_recent_turns(sid, n=self.cfg.short_term_turns)
        recent_tools = self.sessions.load_recent_tool_results(sid, n=40)
        memories = self.sessions.load_memories(sid, max_items=self.cfg.max_memory_items)
        mem_summary = compact_memories(memories)
        workflow = self.planner.build_workflow(user_input=user_input, history=recent_turns)
        skill = self._select_primary_skill(user_input, workflow)
        self._emit(event_callback, {"type": "workflow", "session_id": sid, "workflow": workflow.to_json()})
        self._emit(event_callback, {"type": "skill", "session_id": sid, "skill_id": skill.id, "message": f"primary skill={skill.id}"})

        direct_exec = self._handle_direct_execute_request(
            sid=sid,
            user_input=user_input,
            recent_tools=recent_tools,
            event_callback=event_callback,
        )
        if direct_exec is not None:
            self.sessions.append_turn(sid, Turn(role="user", content=user_input))
            self.sessions.append_turn(sid, Turn(role="assistant", content=direct_exec["reply"]))
            return direct_exec

        plan = self.planner.build_plan(user_input=user_input, history=recent_turns)
        self.sessions.append_plan(sid, plan)
        self._emit(event_callback, {"type": "plan", "session_id": sid, "plan": plan.to_json()})

        tool_results = []
        step_result_map: dict[str, dict] = {}
        for step in plan.steps:
            if step.kind != "tool":
                continue

            # 解析工具输入
            resolved_input = self._resolve_tool_input(step.tool_input, step_result_map)

            # 运行工具
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

            # 存储工具结果
            tool_results.append(payload)
            # 更新工具结果映射
            step_result_map[step.id] = payload
            # 存储工具结果到会话
            self.sessions.append_tool_result(sid, payload)
            self._emit(event_callback, self._event_from_tool_payload(payload))
        
        tool_summary = self._render_tool_summary(tool_results)
        plan_summary = self._render_plan(plan)
        workflow_summary = self._render_workflow(workflow)
        skill_prompt = self._build_skill_prompt_bundle(
            sid=sid,
            task_dir=task_dir,
            workflow=workflow,
            fallback_skill=skill,
            user_input=user_input,
        )

        history_for_prompt = recent_turns + [Turn(role="user", content=user_input)]
        context = build_context(
            user_input=user_input,
            short_term=history_for_prompt,
            memory_summary=mem_summary,
            soul_prompt=self.soul_prompt,
            skill_prompt=skill_prompt,
            plan_summary=workflow_summary + "\n\n" + plan_summary,
            tool_summary=tool_summary,
            max_chars=self.cfg.max_context_chars,
        )
        reply = self.llm.generate(context).text
        auto_save = self._maybe_autosave_generated_file(
            sid=sid,
            task_dir=task_dir,
            user_input=user_input,
            reply=reply,
            workflow=workflow,
        )
        if auto_save is not None:
            write_payload = {
                "ts": utc_now(),
                "step_id": f"s{len(plan.steps) + 1}",
                "depends_on": [],
                "tool": "write_text",
                "planned_input": auto_save["planned_input"],
                "input": auto_save["input"],
                "result": auto_save["result"],
            }
            tool_results.append(write_payload)
            self.sessions.append_tool_result(sid, write_payload)
            self._emit(event_callback, self._event_from_tool_payload(write_payload))

            run_payload = self._maybe_autorun_generated_file(auto_save, step_id=f"s{len(plan.steps) + 2}", event_callback=event_callback)
            if run_payload is not None:
                tool_results.append(run_payload)
                self.sessions.append_tool_result(sid, run_payload)
                self._emit(event_callback, self._event_from_tool_payload(run_payload))

            reply = self._append_autosave_note(reply, write_payload, run_payload)

        promotion_candidate = self._build_promotion_candidate(
            sid=sid,
            user_input=user_input,
            workflow=workflow,
            tool_results=tool_results,
        )
        if promotion_candidate is not None:
            self._save_promotion_candidate(sid, promotion_candidate)
            self._emit(event_callback, {"type": "promotion_candidate", "session_id": sid, "candidate": promotion_candidate})

        self.sessions.append_turn(sid, Turn(role="user", content=user_input))
        self.sessions.append_turn(sid, Turn(role="assistant", content=reply))

        for item in self.extractor.extract(user_input):
            self.sessions.append_memory(sid, item)
        for item in self.extractor.extract(reply):
            self.sessions.append_memory(sid, item)

        return {
            "session_id": sid,
            "skill": skill.name,
            "task_output_dir": str(task_dir),
            "workflow": workflow.to_json(),
            "plan": plan.to_json(),
            "tool_results": tool_results,
            "promotion_candidate": promotion_candidate,
            "reply": reply,
        }

    def run_requirement(
        self,
        requirement: str,
        session_id: str | None = None,
        title: str = "requirement",
        event_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        sid = session_id or self.create_session(title)
        return self.run_turn(requirement, session_id=sid, event_callback=event_callback)

    def _handle_direct_execute_request(
        self,
        *,
        sid: str,
        user_input: str,
        recent_tools: list[dict],
        event_callback: Callable[[dict], None] | None = None,
    ) -> dict | None:
        if not self._is_direct_execute_request(user_input):
            return None
        target_path = self._find_recent_generated_script(recent_tools)
        if not target_path:
            return None

        run_result = self.tools.execute_local_script(
            Path(target_path),
            payload={},
            timeout_sec=30,
            cwd=self._run_cwd_for_script(Path(target_path)),
        )
        self._emit(event_callback, {"type": "run", "session_id": sid, "path": target_path, "exit_code": run_result.get("exit_code"), "stdout": run_result.get("stdout", ""), "stderr": run_result.get("stderr", "")})
        if run_result.get("exit_code") not in {0, None}:
            run_result = self._repair_and_rerun_generated_file(
                user_input=user_input,
                script_path=Path(target_path),
                run_result=run_result,
                max_attempts=2,
                event_callback=event_callback,
            )
        payload = {
            "ts": utc_now(),
            "step_id": "s_exec",
            "depends_on": [],
            "tool": "run_local_script",
            "planned_input": {"path": target_path, "timeout_sec": 30},
            "input": {"path": target_path, "timeout_sec": 30},
            "result": {"ok": True, "data": run_result},
        }
        self.sessions.append_tool_result(sid, payload)
        reply = self._build_direct_execute_reply(target_path, run_result)
        return {
            "session_id": sid,
            "skill": "DirectExecute",
            "plan": {"goal": user_input, "steps": []},
            "tool_results": [payload],
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

    def _render_workflow(self, workflow: WorkflowPlan) -> str:
        rows = [f"workflow goal: {workflow.goal}", f"primary skill: {workflow.primary_skill_id or 'default'}"]
        for task in workflow.tasks:
            dep = f" depends_on={task.depends_on}" if task.depends_on else ""
            skill = f" skill={task.skill_id}" if task.skill_id else ""
            rows.append(f"- {task.id} [{task.kind}]{skill}{dep} -> {task.description}")
        return "\n".join(rows)

    def _select_primary_skill(self, user_input: str, workflow: WorkflowPlan) -> Skill:
        if workflow.primary_skill_id:
            skill = self._skill_by_id(workflow.primary_skill_id)
            if skill is not None:
                return skill
        return self.router.route(user_input, self.skills)

    def _build_skill_prompt_bundle(self, sid: str, task_dir: Path, workflow: WorkflowPlan, fallback_skill: Skill, user_input: str) -> str:
        ordered_ids: list[str] = []
        if workflow.primary_skill_id:
            ordered_ids.append(workflow.primary_skill_id)
        for task in workflow.tasks:
            if task.skill_id and task.skill_id not in ordered_ids:
                ordered_ids.append(task.skill_id)
        prompts: list[str] = []
        seen: set[str] = set()
        for skill_id in ordered_ids:
            skill = self._skill_by_id(skill_id)
            if skill is None or skill.id in seen:
                continue
            prompts.append(f"## Skill:{skill.id}\n{skill.body}")
            seen.add(skill.id)
        if fallback_skill.id not in seen:
            prompts.append(f"## Skill:{fallback_skill.id}\n{fallback_skill.body}")
        if self._should_materialize_code(user_input, workflow):
            prompts.append("## Codegen Rules\n" + self._build_codegen_instruction(user_input, output_root=task_dir))
        return "\n\n".join(prompts)

    def _skill_by_id(self, skill_id: str) -> Skill | None:
        for skill in self.skills:
            if skill.id == skill_id:
                return skill
        return None

    def session_output_dir(self, sid: str) -> Path:
        path = self.cfg.output_dir / sid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_task_output_dir(self, sid: str) -> Path:
        session_root = self.session_output_dir(sid)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = session_root / stamp
        idx = 1
        while path.exists():
            idx += 1
            path = session_root / f"{stamp}_{idx}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _task_scoped_output_path(self, task_dir: Path, raw_path: str) -> str:
        normalized = raw_path.strip().lstrip("./")
        if not normalized:
            return str(task_dir / "generated_script.py")
        return str((task_dir / Path(normalized).name).resolve())

    def _run_cwd_for_script(self, script_path: Path) -> Path:
        resolved = script_path.resolve()
        output_root = self.cfg.output_dir.resolve()
        if output_root in resolved.parents:
            try:
                rel = resolved.relative_to(output_root)
                if len(rel.parts) >= 2:
                    return output_root / rel.parts[0] / rel.parts[1]
            except ValueError:
                pass
        return Path.cwd()

    def _maybe_autosave_generated_file(self, sid: str, task_dir: Path, user_input: str, reply: str, workflow: WorkflowPlan | None = None) -> dict | None:
        if not self._should_materialize_code(user_input, workflow):
            return None
        code_block = self._extract_code_block(reply)
        if code_block is None:
            return None

        code_lang, content = code_block
        target_path = self._infer_output_path(task_dir, user_input, code_lang)
        if not target_path:
            return None

        planned_input = {"path": target_path, "content": "<generated code block>", "mode": "overwrite"}
        real_input = {"path": target_path, "content": content, "mode": "overwrite"}
        result = self.tools.run("write_text", real_input)
        return {
            "planned_input": planned_input,
            "input": real_input,
            "result": result,
            "code_lang": code_lang,
            "user_input": user_input,
        }

    def _maybe_autorun_generated_file(self, auto_save: dict, step_id: str, event_callback: Callable[[dict], None] | None = None) -> dict | None:
        result = auto_save.get("result", {})
        if not result.get("ok"):
            return None
        target_path = (((result.get("data") or {}).get("path")) or "")
        if not target_path:
            return None
        ext = Path(target_path).suffix.lower()
        if ext not in {".py", ".sh", ".js"}:
            return None

        run_result = self.tools.execute_local_script(
            Path(target_path),
            payload={},
            timeout_sec=30,
            cwd=self._run_cwd_for_script(Path(target_path)),
        )
        self._emit(event_callback, {"type": "run", "path": target_path, "exit_code": run_result.get("exit_code"), "stdout": run_result.get("stdout", ""), "stderr": run_result.get("stderr", "")})
        if run_result.get("exit_code") not in {0, None}:
            run_result = self._repair_and_rerun_generated_file(
                user_input=auto_save.get("user_input", ""),
                script_path=Path(target_path),
                run_result=run_result,
                max_attempts=2,
                event_callback=event_callback,
            )
        return {
            "ts": utc_now(),
            "step_id": step_id,
            "depends_on": [],
            "tool": "run_local_script",
            "planned_input": {"path": target_path, "timeout_sec": 30},
            "input": {"path": target_path, "timeout_sec": 30},
            "result": {"ok": True, "data": run_result},
        }

    @staticmethod
    def _should_autosave(user_input: str) -> bool:
        low = user_input.lower()
        create_markers = ["写", "创建", "生成", "保存"]
        file_markers = [".py", ".js", ".sh", "脚本", "python", "文件"]
        return any(token in user_input for token in create_markers) and any(token in low or token in user_input for token in file_markers)

    @classmethod
    def _should_materialize_code(cls, user_input: str, workflow: WorkflowPlan | None = None) -> bool:
        if cls._should_autosave(user_input):
            return True
        if workflow is None:
            return False
        return any(task.kind in {"codegen", "export", "execute"} for task in workflow.tasks)

    @staticmethod
    def _is_direct_execute_request(user_input: str) -> bool:
        text = user_input.strip().lower()
        return text in {"执行", "运行", "帮我执行", "帮我运行", "run it", "execute it"} or (
            any(token in user_input for token in ["执行", "运行"]) and "脚本" not in user_input and "写" not in user_input
        )

    @staticmethod
    def _find_recent_generated_script(recent_tools: list[dict]) -> str:
        for item in reversed(recent_tools):
            if item.get("tool") != "write_text":
                continue
            result = item.get("result") or {}
            if not result.get("ok"):
                continue
            data = result.get("data") or {}
            path = str(data.get("path", ""))
            if Path(path).suffix.lower() in {".py", ".sh", ".js"}:
                return path
        return ""

    @staticmethod
    def _extract_code_block(reply: str) -> tuple[str, str] | None:
        match = re.search(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", reply, flags=re.S)
        if not match:
            return None
        lang = (match.group(1) or "").strip().lower()
        content = match.group(2).strip()
        if not content:
            return None
        return lang, content + "\n"

    def _infer_output_path(self, task_dir: Path, user_input: str, code_lang: str) -> str | None:
        explicit_file = self.planner._extract_path(user_input)
        if explicit_file:
            if explicit_file.endswith("/") or not Path(explicit_file).suffix:
                filename = self._default_filename(user_input, code_lang)
                return self._task_scoped_output_path(task_dir, self._normalize_target_path(explicit_file.rstrip("/") + "/" + filename))
            return self._task_scoped_output_path(task_dir, self._normalize_target_path(explicit_file))

        dir_path = self.planner.extract_dir_path(user_input)
        if not dir_path:
            return str(task_dir / self._default_filename(user_input, code_lang))

        filename = self._default_filename(user_input, code_lang)
        if dir_path.endswith("/"):
            return self._task_scoped_output_path(task_dir, self._normalize_target_path(dir_path + filename))
        return self._task_scoped_output_path(task_dir, self._normalize_target_path(dir_path + "/" + filename))

    @staticmethod
    def _normalize_target_path(path: str) -> str:
        raw = path.strip()
        if re.fullmatch(r"/[\w\-./]+", raw):
            return "." + raw
        return raw

    @staticmethod
    def _default_filename(user_input: str, code_lang: str) -> str:
        low = user_input.lower()
        if "douban" in low or "豆瓣" in user_input:
            stem = "douban_scraper"
        elif "ppt" in low:
            stem = "generate_ppt"
        elif "crawl" in low or "爬" in user_input:
            stem = "web_scraper"
        else:
            stem = "generated_script"

        ext = {
            "python": ".py",
            "py": ".py",
            "javascript": ".js",
            "js": ".js",
            "bash": ".sh",
            "sh": ".sh",
        }.get(code_lang, ".py")
        return stem + ext

    @staticmethod
    def _build_codegen_instruction(user_input: str, output_root: Path) -> str:
        parts = [
            "For code-generation requests, return exactly one fenced code block with runnable code.",
            "The code must be complete and executable without placeholders.",
            f"The process working directory is already the task output root: {output_root}",
            "Write generated artifacts directly into the current working directory using only file names like `news.xlsx`, `result.csv`, or `report.json`.",
            "Do not prepend `output/`, session ids, timestamps, or recreate parent folders in generated code.",
            "If the user names a target directory, treat it only as a naming hint. Do not create nested folders from it.",
            "If the task fetches many records, print only a small preview and a summary count.",
        ]
        low = user_input.lower()
        if "excel" in low or "xlsx" in low:
            parts.append("If the user asks for Excel output, write an .xlsx file to the target directory.")
        if "豆瓣" in user_input or "douban" in low:
            parts.append("For Douban scraping, include request headers and graceful error handling.")
        return "\n".join(parts)

    @staticmethod
    def _build_direct_execute_reply(script_path: str, run_data: dict) -> str:
        lines = [
            f"已执行脚本：`{script_path}`",
            f"退出码：{run_data.get('exit_code')}",
        ]
        if run_data.get("auto_installed"):
            lines.append(f"自动安装依赖：`{run_data['auto_installed']}`")
        stdout = str(run_data.get("stdout", "")).strip()
        stderr = str(run_data.get("stderr", "")).strip()
        if stdout:
            lines.append("输出概览：")
            preview = stdout.splitlines()[:10]
            lines.extend(preview)
            if len(stdout.splitlines()) > 10:
                lines.append("... (仅展示前10行)")
        if stderr:
            lines.append("错误输出：")
            lines.append(stderr[:500])
        repairs = run_data.get("repairs") or []
        if repairs:
            lines.append(f"自动修复次数：{len(repairs)}")
        return "\n".join(lines)

    @staticmethod
    def _append_autosave_note(reply: str, payload: dict, run_payload: dict | None) -> str:
        result = payload.get("result", {})
        data = result.get("data", {}) if isinstance(result, dict) else {}
        if result.get("ok"):
            path = data.get("path", "")
            note = f"\n\n已将生成内容写入文件：`{path}`"
            if run_payload is not None:
                run_data = ((run_payload.get("result") or {}).get("data") or {})
                note += AgentExecutor._format_run_note(run_data)
            return reply.rstrip() + note
        return reply.rstrip() + f"\n\n尝试写入文件失败：{result.get('error', 'unknown error')}"

    @staticmethod
    def _format_run_note(run_data: dict) -> str:
        exit_code = run_data.get("exit_code")
        script = run_data.get("script", "")
        stdout = str(run_data.get("stdout", "")).strip()
        stderr = str(run_data.get("stderr", "")).strip()
        note = f"\n已使用虚拟环境尝试执行：`{script}`，退出码：{exit_code}"
        if run_data.get("auto_installed"):
            note += f"\n自动安装依赖：`{run_data['auto_installed']}`"
        if stdout:
            note += f"\nstdout: {stdout[:300]}"
        if stderr:
            note += f"\nstderr: {stderr[:300]}"
        install = run_data.get("install")
        if isinstance(install, dict) and not install.get("ok", True):
            note += f"\n依赖安装失败：{install.get('stderr') or install.get('stdout') or install.get('error', 'unknown error')}"
        repairs = run_data.get("repairs") or []
        if repairs:
            note += f"\n自动修复次数：{len(repairs)}"
        return note

    def _build_promotion_candidate(self, *, sid: str, user_input: str, workflow: WorkflowPlan, tool_results: list[dict]) -> dict | None:
        if not any(task.kind in {"codegen", "execute", "export"} for task in workflow.tasks):
            return None
        script_path = ""
        for item in reversed(tool_results):
            if item.get("tool") != "write_text":
                continue
            result = item.get("result") or {}
            if not result.get("ok"):
                continue
            data = result.get("data") or {}
            path = str(data.get("path", ""))
            if Path(path).suffix.lower() in {".py", ".js", ".sh"}:
                script_path = path
                break
        if not script_path:
            return None
        run_ok = False
        for item in reversed(tool_results):
            if item.get("tool") != "run_local_script":
                continue
            data = ((item.get("result") or {}).get("data") or {})
            if str(data.get("script", "")) == script_path and data.get("exit_code") == 0:
                run_ok = True
                break
        if not run_ok:
            return None
        base_name = Path(script_path).stem
        candidate = {
            "session_id": sid,
            "source_request": user_input,
            "script_path": script_path,
            "suggested_skill_id": f"learned__{base_name}",
            "suggested_name": base_name.replace("_", " ").title(),
            "status": "pending_confirmation",
        }
        return candidate

    def _save_promotion_candidate(self, sid: str, candidate: dict) -> None:
        target = self.session_output_dir(sid) / "promotion_candidate.json"
        target.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_promotion_candidate(self, sid: str) -> dict | None:
        target = self.session_output_dir(sid) / "promotion_candidate.json"
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def promote_session_candidate_to_skill(
        self,
        sid: str,
        *,
        approve: bool,
        skill_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        triggers: list[str] | None = None,
    ) -> dict:
        candidate = self.load_promotion_candidate(sid)
        if candidate is None:
            return {"ok": False, "error": "no promotion candidate for session"}
        if not approve:
            candidate["status"] = "rejected"
            self._save_promotion_candidate(sid, candidate)
            return {"ok": True, "status": "rejected"}

        src = Path(candidate["script_path"])
        if not src.exists():
            return {"ok": False, "error": f"source script not found: {src}"}

        final_skill_id = skill_id or candidate["suggested_skill_id"]
        skill_dir = Path(self.cfg.skills_dir) / final_skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("scripts", "references", "assets"):
            (skill_dir / sub).mkdir(parents=True, exist_ok=True)
            (skill_dir / sub / ".gitkeep").touch(exist_ok=True)

        dst_script = skill_dir / "scripts" / src.name
        dst_script.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        skill_md = skill_dir / "SKILL.md"
        trigger_text = ",".join(triggers or [])
        skill_md.write_text(
            "---\n"
            f"id: {final_skill_id}\n"
            f"name: {name or candidate['suggested_name']}\n"
            f"description: {description or ('learned skill from session ' + sid)}\n"
            f"triggers: {trigger_text}\n"
            "---\n"
            "You are a learned task skill.\n"
            "Rules:\n"
            "1. Reuse the packaged script when the task matches this learned pattern.\n"
            "2. Keep outputs deterministic and stored under the active session output directory.\n"
            "3. Prefer execution and artifact delivery over long explanations.\n",
            encoding="utf-8",
        )
        candidate["status"] = "approved"
        candidate["approved_skill_id"] = final_skill_id
        self._save_promotion_candidate(sid, candidate)
        self.skills = load_skills(Path(self.cfg.skills_dir))
        self.skill_script_index = self._build_skill_script_index(self.skills)
        self.tools.script_index = self.skill_script_index
        return {"ok": True, "status": "approved", "skill_id": final_skill_id, "skill_dir": str(skill_dir)}

    def _repair_and_rerun_generated_file(
        self,
        *,
        user_input: str,
        script_path: Path,
        run_result: dict,
        max_attempts: int = 2,
        event_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        current = dict(run_result)
        repairs: list[dict] = []
        for attempt in range(1, max_attempts + 1):
            if current.get("exit_code") == 0:
                break
            try:
                source = script_path.read_text(encoding="utf-8")
            except OSError:
                break
            repair_reply = self.llm.generate(
                self._build_repair_prompt(
                    user_input=user_input,
                    script_path=script_path,
                    source=source,
                    run_result=current,
                )
            ).text
            code_block = self._extract_code_block(repair_reply)
            if code_block is None:
                repairs.append({"attempt": attempt, "status": "no_code_block"})
                break
            _, fixed_code = code_block
            write_result = self.tools.run(
                "write_text",
                {"path": str(script_path), "content": fixed_code, "mode": "overwrite"},
            )
            rerun = self.tools.execute_local_script(
                script_path,
                payload={},
                timeout_sec=30,
                cwd=self._run_cwd_for_script(script_path),
            )
            self._emit(
                event_callback,
                {
                    "type": "repair",
                    "script": str(script_path),
                    "attempt": attempt,
                    "exit_code": rerun.get("exit_code"),
                    "stdout": rerun.get("stdout", ""),
                    "stderr": rerun.get("stderr", ""),
                },
            )
            repairs.append(
                {
                    "attempt": attempt,
                    "write_ok": write_result.get("ok"),
                    "exit_code": rerun.get("exit_code"),
                    "stderr": str(rerun.get("stderr", ""))[:300],
                }
            )
            current = rerun
        current["repairs"] = repairs
        return current

    @staticmethod
    def _emit(event_callback: Callable[[dict], None] | None, event: dict) -> None:
        if event_callback is None:
            return
        event_callback(event)

    @staticmethod
    def _event_from_tool_payload(payload: dict) -> dict:
        result = payload.get("result", {}) or {}
        data = result.get("data", {}) if isinstance(result, dict) else {}
        return {
            "type": "tool",
            "step_id": payload.get("step_id"),
            "tool": payload.get("tool"),
            "ok": result.get("ok"),
            "path": data.get("path") if isinstance(data, dict) else "",
            "script": data.get("script") if isinstance(data, dict) else "",
            "exit_code": data.get("exit_code") if isinstance(data, dict) else None,
        }

    @staticmethod
    def _build_repair_prompt(*, user_input: str, script_path: Path, source: str, run_result: dict) -> str:
        return (
            "You are fixing a generated local script.\n"
            "Return exactly one fenced code block with the full corrected file.\n"
            "Keep the original task intent, preserve the target output path behavior, and make it runnable.\n"
            "The script is executed with its task output directory as the current working directory.\n"
            "Use direct file names for artifacts. Do not prepend output/, session ids, timestamps, or recreate parent folders.\n\n"
            f"User request:\n{user_input}\n\n"
            f"Script path:\n{script_path}\n\n"
            f"Current source:\n```python\n{source}\n```\n\n"
            f"Execution stderr:\n{run_result.get('stderr', '')}\n\n"
            f"Execution stdout:\n{run_result.get('stdout', '')}\n"
        )

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
