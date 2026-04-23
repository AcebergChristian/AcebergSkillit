from __future__ import annotations

import re

from .schema import Plan, PlanStep, Turn


class Planner:
    """Mandatory planning before any tool execution."""

    OPS = {
        "list_files": ["list", "ls", "目录", "文件列表", "列出"],
        "read_text": ["read", "查看", "读取", "内容"],
        "search_text": ["search", "grep", "查找", "搜索"],
        "write_text": ["write", "创建", "写入", "保存"],
    }

    def build_plan(self, user_input: str, history: list[Turn]) -> Plan:
        text = user_input.strip()
        steps: list[PlanStep] = [
            PlanStep(
                id="s1",
                kind="analyze",
                description="Clarify user goal and constraints from latest turns.",
            )
        ]

        tool_steps = self._infer_tool_steps(text)
        for i, step in enumerate(tool_steps, start=2):
            step.id = f"s{i}"
            if i > 2:
                step.depends_on = [f"s{i - 1}"]
            steps.append(step)

        steps.append(
            PlanStep(
                id=f"s{len(steps) + 1}",
                kind="respond",
                description="Generate final response grounded in tool outputs and memory.",
            )
        )
        return Plan(goal=text, steps=steps)

    def _infer_tool_steps(self, text: str) -> list[PlanStep]:
        ordered_ops = self._infer_ops_order(text)
        if not ordered_ops:
            return []

        path = self._extract_path(text) or "."
        pattern = self._extract_pattern(text) or text[:30]

        steps: list[PlanStep] = []
        for op in ordered_ops:
            if op == "list_files":
                steps.append(
                    PlanStep(
                        id="",
                        kind="tool",
                        description="List files for requested scope.",
                        tool="list_files",
                        tool_input={"path": path},
                    )
                )

            elif op == "search_text":
                steps.append(
                    PlanStep(
                        id="",
                        kind="tool",
                        description="Search keyword in requested scope.",
                        tool="search_text",
                        tool_input={"path": path, "pattern": pattern},
                    )
                )

            elif op == "read_text":
                read_path = self._extract_path(text)
                if not read_path and any(s.tool == "search_text" for s in steps):
                    read_path = "{{last_search_hit_file}}"
                if read_path:
                    steps.append(
                        PlanStep(
                            id="",
                            kind="tool",
                            description="Read target file content.",
                            tool="read_text",
                            tool_input={"path": read_path},
                        )
                    )

            elif op == "write_text":
                write_path = self._extract_path(text) or "./output.txt"
                steps.append(
                    PlanStep(
                        id="",
                        kind="tool",
                        description="Write requested content into file.",
                        tool="write_text",
                        tool_input={"path": write_path, "content": text},
                    )
                )

        return steps

    def _infer_ops_order(self, text: str) -> list[str]:
        low = text.lower()
        points: list[tuple[int, str]] = []
        for op, keys in self.OPS.items():
            pos = -1
            for k in keys:
                p = low.find(k)
                if p != -1 and (pos == -1 or p < pos):
                    pos = p
            if pos != -1:
                points.append((pos, op))
        points.sort(key=lambda x: x[0])
        return [op for _, op in points]

    @staticmethod
    def _extract_path(text: str) -> str | None:
        backtick = re.search(r"`([^`]+)`", text)
        if backtick:
            return backtick.group(1).strip()
        maybe = re.search(r"([./][\w./\-]+\.[a-zA-Z0-9]+)", text)
        if maybe:
            return maybe.group(1).strip()
        return None

    @staticmethod
    def _extract_pattern(text: str) -> str | None:
        quoted = re.search(r'"([^"]+)"', text)
        if quoted:
            return quoted.group(1).strip()
        single = re.search(r"'([^']+)'", text)
        if single:
            return single.group(1).strip()
        return None
