from __future__ import annotations

import re
from pathlib import Path

from .compressor import build_context
from .config import RuntimeConfig, load_dotenv
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
            references=[],
            assets=[],
        )


class AgentExecutor:
    def __init__(self, cfg: RuntimeConfig | None = None, llm: BaseLLM | None = None) -> None:
        load_dotenv()
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
    def run_turn(self, user_input: str, session_id: str | None = None) -> dict:
        sid = self.sessions.ensure(session_id)
        skill = self.router.route(user_input, self.skills)

        recent_turns = self.sessions.load_recent_turns(sid, n=self.cfg.short_term_turns)
        recent_tools = self.sessions.load_recent_tool_results(sid, n=40)
        memories = self.sessions.load_memories(sid, max_items=self.cfg.max_memory_items)
        mem_summary = compact_memories(memories)

        direct_exec = self._handle_direct_execute_request(
            sid=sid,
            user_input=user_input,
            recent_tools=recent_tools,
        )
        if direct_exec is not None:
            self.sessions.append_turn(sid, Turn(role="user", content=user_input))
            self.sessions.append_turn(sid, Turn(role="assistant", content=direct_exec["reply"]))
            return direct_exec

        plan = self.planner.build_plan(user_input=user_input, history=recent_turns)
        self.sessions.append_plan(sid, plan)

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
        
        tool_summary = self._render_tool_summary(tool_results)
        plan_summary = self._render_plan(plan)
        skill_prompt = skill.body
        if self._should_autosave(user_input):
            skill_prompt = skill_prompt.rstrip() + "\n\n" + self._build_codegen_instruction(user_input)

        history_for_prompt = recent_turns + [Turn(role="user", content=user_input)]
        context = build_context(
            user_input=user_input,
            short_term=history_for_prompt,
            memory_summary=mem_summary,
            soul_prompt=self.soul_prompt,
            skill_prompt=skill_prompt,
            plan_summary=plan_summary,
            tool_summary=tool_summary,
            max_chars=self.cfg.max_context_chars,
        )
        reply = self.llm.generate(context).text
        auto_save = self._maybe_autosave_generated_file(user_input, reply)
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

            run_payload = self._maybe_autorun_generated_file(auto_save, step_id=f"s{len(plan.steps) + 2}")
            if run_payload is not None:
                tool_results.append(run_payload)
                self.sessions.append_tool_result(sid, run_payload)

            reply = self._append_autosave_note(reply, write_payload, run_payload)

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

    def _handle_direct_execute_request(self, *, sid: str, user_input: str, recent_tools: list[dict]) -> dict | None:
        if not self._is_direct_execute_request(user_input):
            return None
        target_path = self._find_recent_generated_script(recent_tools)
        if not target_path:
            return None

        run_result = self.tools.execute_local_script(Path(target_path), payload={}, timeout_sec=30)
        if run_result.get("exit_code") not in {0, None}:
            run_result = self._repair_and_rerun_generated_file(
                user_input=user_input,
                script_path=Path(target_path),
                run_result=run_result,
                max_attempts=2,
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

    def _maybe_autosave_generated_file(self, user_input: str, reply: str) -> dict | None:
        if not self._should_autosave(user_input):
            return None
        code_block = self._extract_code_block(reply)
        if code_block is None:
            return None

        code_lang, content = code_block
        target_path = self._infer_output_path(user_input, code_lang)
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

    def _maybe_autorun_generated_file(self, auto_save: dict, step_id: str) -> dict | None:
        result = auto_save.get("result", {})
        if not result.get("ok"):
            return None
        target_path = (((result.get("data") or {}).get("path")) or "")
        if not target_path:
            return None
        ext = Path(target_path).suffix.lower()
        if ext not in {".py", ".sh", ".js"}:
            return None

        run_result = self.tools.execute_local_script(Path(target_path), payload={}, timeout_sec=30)
        if run_result.get("exit_code") not in {0, None}:
            run_result = self._repair_and_rerun_generated_file(
                user_input=auto_save.get("user_input", ""),
                script_path=Path(target_path),
                run_result=run_result,
                max_attempts=2,
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

    def _infer_output_path(self, user_input: str, code_lang: str) -> str | None:
        explicit_file = self.planner._extract_path(user_input)
        if explicit_file:
            if explicit_file.endswith("/") or not Path(explicit_file).suffix:
                filename = self._default_filename(user_input, code_lang)
                return self._normalize_target_path(explicit_file.rstrip("/") + "/" + filename)
            return self._normalize_target_path(explicit_file)

        dir_path = self.planner.extract_dir_path(user_input)
        if not dir_path:
            return None

        filename = self._default_filename(user_input, code_lang)
        if dir_path.endswith("/"):
            return self._normalize_target_path(dir_path + filename)
        return self._normalize_target_path(dir_path + "/" + filename)

    @staticmethod
    def _normalize_target_path(path: str) -> str:
        raw = path.strip()
        if re.fullmatch(r"/[\w\-/]+", raw):
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
    def _build_codegen_instruction(user_input: str) -> str:
        parts = [
            "For code-generation requests, return exactly one fenced code block with runnable code.",
            "The code must be complete and executable without placeholders.",
            "When the user names a target directory, save any output files into that same directory.",
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

    def _repair_and_rerun_generated_file(
        self,
        *,
        user_input: str,
        script_path: Path,
        run_result: dict,
        max_attempts: int = 2,
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
            rerun = self.tools.execute_local_script(script_path, payload={}, timeout_sec=30)
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
    def _build_repair_prompt(*, user_input: str, script_path: Path, source: str, run_result: dict) -> str:
        return (
            "You are fixing a generated local script.\n"
            "Return exactly one fenced code block with the full corrected file.\n"
            "Keep the original task intent, preserve the target output path behavior, and make it runnable.\n\n"
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
