from __future__ import annotations

from pathlib import Path


class ToolRegistry:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def list_tools(self) -> list[dict]:
        return [
            {"name": "list_files", "desc": "List files and folders under a path."},
            {"name": "read_text", "desc": "Read text content from a file."},
            {"name": "search_text", "desc": "Search keyword in files recursively."},
            {"name": "write_text", "desc": "Write or append text to a file."},
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

    def _safe_path(self, raw: str) -> Path:
        if not raw:
            raw = "."
        p = (self.workspace_root / raw).resolve() if not raw.startswith("/") else Path(raw).resolve()
        if self.workspace_root not in p.parents and p != self.workspace_root:
            raise ValueError(f"path out of workspace: {raw}")
        return p
