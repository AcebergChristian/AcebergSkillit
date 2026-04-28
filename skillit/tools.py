from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


class ToolRegistry:
    def __init__(self, workspace_root: Path, script_index: dict[str, dict[str, str]] | None = None) -> None:
        self.workspace_root = workspace_root.resolve()
        self.script_index = script_index or {}
        self.venv_python = self.workspace_root / ".venv" / "bin" / "python"
        self.venv_pip = self.workspace_root / ".venv" / "bin" / "pip"

    def list_tools(self) -> list[dict]:
        return [
            {"name": "list_files", "desc": "List files and folders under a path."},
            {"name": "read_text", "desc": "Read text content from a file."},
            {"name": "search_text", "desc": "Search keyword in files recursively."},
            {"name": "write_text", "desc": "Write or append text to a file."},
            {"name": "run_local_script", "desc": "Run a local .py/.sh/.js file, preferring .venv for Python."},
            {
                "name": "run_skill_script",
                "desc": "Run a local script from skills/<skill>/scripts/ inside a skill pack.",
            },
        ]

    def run(self, name: str, params: dict) -> dict:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            return {"ok": True, "data": handler(params)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def tool_list_files(self, params: dict) -> dict:
        target = self._safe_path(params.get("path", "."))
        entries = []
        for p in sorted(target.iterdir()):
            entries.append({"name": p.name, "is_dir": p.is_dir()})
        return {"path": str(target), "entries": entries[:200]}

    def tool_read_text(self, params: dict) -> dict:
        target = self._safe_path(params["path"])
        max_chars = int(params.get("max_chars", 4000))
        text = target.read_text(encoding="utf-8")
        return {"path": str(target), "content": text[:max_chars]}

    def tool_search_text(self, params: dict) -> dict:
        base = self._safe_path(params.get("path", "."))
        pattern = str(params.get("pattern", "")).lower().strip()
        hits = []
        if not pattern:
            return {"hits": hits}

        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            if any(skip in p.parts for skip in [".git", "__pycache__", ".venv"]):
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            for idx, line in enumerate(content.splitlines(), start=1):
                if pattern in line.lower():
                    hits.append({"file": str(p), "line": idx, "text": line[:200]})
                if len(hits) >= int(params.get("max_hits", 40)):
                    return {"hits": hits}
        return {"hits": hits}

    def tool_write_text(self, params: dict) -> dict:
        target = self._safe_path(params["path"])
        mode = str(params.get("mode", "overwrite"))
        content = str(params.get("content", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with target.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            target.write_text(content, encoding="utf-8")
        return {"path": str(target), "size": len(content), "mode": mode}

    def tool_run_skill_script(self, params: dict) -> dict:
        timeout_sec = int(params.get("timeout_sec", 20))
        payload = params.get("input", {})
        script_path = self._resolve_script_path(params)
        return self.execute_local_script(script_path, payload=payload, timeout_sec=timeout_sec)

    def execute_local_script(self, script_path: Path, payload: dict | None = None, timeout_sec: int = 20) -> dict:
        payload = payload or {}
        first_run = self._run_local_script_once(script_path, payload=payload, timeout_sec=timeout_sec)
        missing_module = self._extract_missing_module(first_run)
        if missing_module and self.venv_pip.exists():
            install = self._install_package(missing_module, timeout_sec=timeout_sec)
            if install["ok"]:
                second_run = self._run_local_script_once(script_path, payload=payload, timeout_sec=timeout_sec)
                second_run["auto_installed"] = missing_module
                second_run["install"] = install
                return second_run
            first_run["install"] = install
        return first_run

    def _run_local_script_once(self, script_path: Path, payload: dict | None = None, timeout_sec: int = 20) -> dict:
        payload = payload or {}
        cmd = self._build_cmd(script_path)
        env = dict(os.environ)
        env["SKILLIT_INPUT_JSON"] = json.dumps(payload, ensure_ascii=False)

        proc = subprocess.run(
            cmd,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            env=env,
            cwd=str(script_path.parent),
        )

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        parsed_stdout = self._maybe_json(stdout)

        return {
            "script": str(script_path),
            "exit_code": proc.returncode,
            "stdout": parsed_stdout,
            "stderr": stderr,
            "cmd": cmd,
        }

    def _resolve_script_path(self, params: dict) -> Path:
        # Option A: direct path
        raw = params.get("path")
        if raw:
            return self._safe_path(str(raw))

        # Option B: skill + script name
        skill = str(params.get("skill", "")).strip().lower()
        script = str(params.get("script", "")).strip()
        if not skill or not script:
            raise ValueError("run_skill_script requires path, or skill+script")
        script_map = self.script_index.get(skill, {})
        real = script_map.get(script)
        if not real:
            raise ValueError(f"script not found: skill={skill} script={script}")
        return self._safe_path(real)

    def _build_cmd(self, script_path: Path) -> list[str]:
        ext = script_path.suffix.lower()
        if ext == ".py":
            py = str(self.venv_python if self.venv_python.exists() else Path(sys.executable))
            return [py, str(script_path)]
        if ext == ".sh":
            return ["/bin/sh", str(script_path)]
        if ext == ".js":
            return ["node", str(script_path)]
        return [str(script_path)]

    def _install_package(self, package: str, timeout_sec: int = 20) -> dict:
        if not self.venv_pip.exists():
            return {"ok": False, "error": "missing .venv/bin/pip", "package": package}
        proc = subprocess.run(
            [str(self.venv_pip), "install", package],
            text=True,
            capture_output=True,
            timeout=max(timeout_sec, 60),
            cwd=str(self.workspace_root),
            env=dict(os.environ),
        )
        return {
            "ok": proc.returncode == 0,
            "package": package,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "").strip()[:1200],
            "stderr": (proc.stderr or "").strip()[:1200],
        }

    @staticmethod
    def _extract_missing_module(run_result: dict) -> str | None:
        stderr = str(run_result.get("stderr", ""))
        stdout = str(run_result.get("stdout", ""))
        text = stderr + "\n" + stdout
        m = re.search(r"No module named ['\"]([^'\"]+)['\"]", text)
        if not m:
            return None
        name = m.group(1).strip()
        if not name or "." in name:
            return name.split(".", 1)[0] if name else None
        return name

    @staticmethod
    def _maybe_json(text: str):
        if not text:
            return ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def _safe_path(self, raw: str) -> Path:
        if not raw:
            raw = "."
        p = (self.workspace_root / raw).resolve() if not raw.startswith("/") else Path(raw).resolve()
        if self.workspace_root not in p.parents and p != self.workspace_root:
            raise ValueError(f"path out of workspace: {raw}")
        return p
