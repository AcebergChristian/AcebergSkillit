from __future__ import annotations

import ast
import json
import os
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(slots=True)
class LLMReply:
    text: str
    model: str


@dataclass(slots=True)
class LLMHealth:
    provider: str
    mode: str
    model: str
    api_style: str
    base_url: str
    api_key_present: bool
    api_key_masked: str
    timeout_sec: int
    endpoint: str


@dataclass(slots=True)
class LLMProbe:
    ok: bool
    status: str
    detail: str
    endpoint: str
    model: str


class BaseLLM:
    def generate(self, prompt: str) -> LLMReply:
        raise NotImplementedError

    def health(self) -> LLMHealth:
        return LLMHealth(
            provider=self.__class__.__name__,
            mode="offline",
            model="unknown",
            api_style="unknown",
            base_url="",
            api_key_present=False,
            api_key_masked="(missing)",
            timeout_sec=0,
            endpoint="",
        )

    def probe(self) -> LLMProbe:
        health = self.health()
        return LLMProbe(
            ok=False,
            status="unsupported",
            detail="probe is not supported for this provider",
            endpoint=health.endpoint,
            model=health.model,
        )


class EchoLLM(BaseLLM):
    """Offline fallback that avoids leaking the full prompt."""

    def __init__(self, reason: str = "offline") -> None:
        self.reason = reason

    def generate(self, prompt: str) -> LLMReply:
        user_input = _extract_section(prompt, "New User Input") or "(empty)"
        tool_results = _extract_section(prompt, "Tool Results")
        intro = _offline_intro(self.reason)

        tool_reply = _build_offline_tool_reply(tool_results)
        if tool_reply:
            text = f"{intro}\n\n{tool_reply}"
        else:
            text = (
                f"{intro}\n\n"
                f"你的请求是：{user_input}\n"
                "当前离线模式不会生成真实 AI 回答。"
            )
        return LLMReply(text=text, model="echo")

    def health(self) -> LLMHealth:
        return LLMHealth(
            provider="EchoLLM",
            mode="offline",
            model="echo",
            api_style="local",
            base_url="",
            api_key_present=False,
            api_key_masked="(missing)",
            timeout_sec=0,
            endpoint="",
        )

    def probe(self) -> LLMProbe:
        health = self.health()
        return LLMProbe(
            ok=False,
            status="offline",
            detail="EchoLLM is a local fallback and cannot probe a remote endpoint",
            endpoint=health.endpoint,
            model=health.model,
        )


class OpenAIResponsesLLM(BaseLLM):
    def __init__(self, model: str = "gpt-5.4-mini") -> None:
        self.model = os.getenv("SKILLIT_MODEL", model)
        self.api_key = os.getenv("SKILLIT_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (os.getenv("SKILLIT_BASE_URL", "https://api.openai.com/v1") or "").rstrip("/")
        self.api_style = (os.getenv("SKILLIT_API_STYLE", "responses") or "responses").strip().lower()
        if self.api_style in {"chat", "chat/completions"}:
            self.api_style = "chat_completions"
        self.timeout_sec = int(os.getenv("SKILLIT_TIMEOUT_SEC", "60"))

    def generate(self, prompt: str) -> LLMReply:
        if not self.api_key:
            return EchoLLM(reason="missing_api_key").generate(prompt)

        if self.api_style == "chat_completions":
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
        else:
            url = f"{self.base_url}/responses"
            payload = {
                "model": self.model,
                "input": prompt,
            }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return EchoLLM(reason=f"http_error:{e.code}").generate(prompt)
        except (TimeoutError, socket.timeout):
            return EchoLLM(reason="timeout").generate(prompt)
        except urllib.error.URLError:
            return EchoLLM(reason="network_error").generate(prompt)

        text = ""
        if self.api_style == "chat_completions":
            choices = data.get("choices", [])
            if choices:
                text = (((choices[0] or {}).get("message") or {}).get("content") or "").strip()
        else:
            text = (data.get("output_text") or "").strip()

        if not text:
            text = "(empty response)"
        return LLMReply(text=text, model=self.model)

    def health(self) -> LLMHealth:
        endpoint = "/chat/completions" if self.api_style == "chat_completions" else "/responses"
        return LLMHealth(
            provider="OpenAIResponsesLLM",
            mode="online" if bool(self.api_key) else "offline-fallback",
            model=self.model,
            api_style=self.api_style,
            base_url=self.base_url,
            api_key_present=bool(self.api_key),
            api_key_masked=_mask_secret(self.api_key),
            timeout_sec=self.timeout_sec,
            endpoint=f"{self.base_url}{endpoint}" if self.base_url else endpoint,
        )

    def probe(self) -> LLMProbe:
        health = self.health()
        if not self.api_key:
            return LLMProbe(
                ok=False,
                status="missing_api_key",
                detail="SKILLIT_API_KEY or OPENAI_API_KEY is missing",
                endpoint=health.endpoint,
                model=health.model,
            )

        timeout_sec = min(self.timeout_sec, 10)
        if self.api_style == "chat_completions":
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
        else:
            url = f"{self.base_url}/responses"
            payload = {
                "model": self.model,
                "input": "ping",
                "max_output_tokens": 1,
            }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = _read_http_error(e)
            return LLMProbe(
                ok=False,
                status=f"http_{e.code}",
                detail=detail or f"HTTP {e.code}",
                endpoint=url,
                model=self.model,
            )
        except (TimeoutError, socket.timeout):
            return LLMProbe(
                ok=False,
                status="timeout",
                detail=f"request timed out after {timeout_sec}s",
                endpoint=url,
                model=self.model,
            )
        except urllib.error.URLError as e:
            return LLMProbe(
                ok=False,
                status="network_error",
                detail=str(getattr(e, "reason", e)),
                endpoint=url,
                model=self.model,
            )

        if self.api_style == "chat_completions":
            choices = data.get("choices", [])
            ok = bool(choices)
            detail = "chat_completions returned choices" if ok else "chat_completions returned no choices"
        else:
            ok = "output" in data or "output_text" in data
            detail = "responses endpoint returned output payload" if ok else "responses endpoint returned unexpected payload"
        return LLMProbe(
            ok=ok,
            status="ok" if ok else "unexpected_payload",
            detail=detail,
            endpoint=url,
            model=self.model,
        )


def _extract_section(prompt: str, title: str) -> str:
    pattern = rf"(?ms)^# {re.escape(title)}\n(.*?)(?=^# |\Z)"
    matches = re.findall(pattern, prompt)
    if not matches:
        return ""
    return matches[-1].strip()


def _build_offline_tool_reply(tool_summary: str) -> str:
    if not tool_summary or tool_summary == "(no tool called)":
        return ""

    lines = [line.strip() for line in tool_summary.splitlines() if line.strip()]
    rendered: list[str] = []
    for line in lines[:3]:
        rendered_line = _render_tool_line(line)
        if rendered_line:
            rendered.append(rendered_line)

    if not rendered:
        return "已执行本地工具，但离线模式下无法生成进一步的自然语言分析。"
    return "已根据本地工具执行结果给出答复：\n" + "\n".join(rendered)


def _render_tool_line(line: str) -> str:
    match = re.match(r"^\[(?P<step>[^\]]+)\]\s+(?P<tool>\w+)\s+=>\s+(?P<body>.*)$", line)
    if not match:
        return f"- {line[:240]}"

    tool = match.group("tool")
    body = match.group("body")
    try:
        payload = ast.literal_eval(body)
    except (SyntaxError, ValueError):
        return f"- `{tool}` 已执行。"

    if not isinstance(payload, dict):
        return f"- `{tool}` 已执行。"
    if not payload.get("ok"):
        return f"- `{tool}` 执行失败：{payload.get('error', 'unknown error')}"

    data = payload.get("data")
    if tool == "list_files" and isinstance(data, dict):
        entries = data.get("entries") or []
        names = [item.get("name", "") for item in entries[:8] if isinstance(item, dict)]
        path = data.get("path", ".")
        return f"- 目录 `{path}` 下包含：{', '.join([n for n in names if n]) or '(empty)' }"

    if tool == "read_text" and isinstance(data, dict):
        path = data.get("path", "")
        content = str(data.get("content", "")).strip().replace("\n", " ")
        return f"- 文件 `{path}` 内容摘要：{content[:220] or '(empty)'}"

    if tool == "search_text" and isinstance(data, dict):
        hits = data.get("hits") or []
        if not hits:
            return "- 没有搜索到匹配结果。"
        first = hits[0] if isinstance(hits[0], dict) else {}
        return f"- 搜索命中 {len(hits)} 条，首条在 `{first.get('file', '')}` 第 {first.get('line', '?')} 行。"

    if tool == "write_text" and isinstance(data, dict):
        return f"- 已写入文件 `{data.get('path', '')}`，模式 `{data.get('mode', 'overwrite')}`。"

    if tool == "run_skill_script" and isinstance(data, dict):
        stdout = str(data.get("stdout", "")).strip().replace("\n", " ")
        stderr = str(data.get("stderr", "")).strip().replace("\n", " ")
        if stdout:
            return f"- 脚本 `{data.get('script', '')}` 输出：{stdout[:220]}"
        if stderr:
            return f"- 脚本 `{data.get('script', '')}` 报错：{stderr[:220]}"
        return f"- 脚本 `{data.get('script', '')}` 已执行，退出码 {data.get('exit_code', '?')}。"

    return f"- `{tool}` 已执行。"


def _mask_secret(value: str) -> str:
    if not value:
        return "(missing)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _read_http_error(err: urllib.error.HTTPError) -> str:
    try:
        body = err.read().decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        body = ""
    return body[:400]


def _offline_intro(reason: str) -> str:
    if reason == "missing_api_key":
        return (
            "当前未配置 `SKILLIT_API_KEY` 或 `OPENAI_API_KEY`，已切换到离线模式。\n"
            "请直接执行下面这些命令完成配置：\n"
            "1. `skillit config set api-key \"你的新key\"`\n"
            "2. `skillit config set base-url \"https://dashscope.aliyuncs.com/compatible-mode/v1\"`\n"
            "3. `skillit config set model \"qwen-plus\"`\n"
            "4. `skillit config set api-style \"chat_completions\"`\n"
            "5. `skillit config probe`\n"
            "配置完成后，重新运行 `skillit`。"
        )
    if reason == "network_error":
        return (
            "模型请求失败，已切换到离线模式。\n"
            "请执行 `skillit config probe` 检查当前 endpoint 是否可达。"
        )
    if reason == "timeout":
        return (
            "模型请求超时，已切换到离线模式。\n"
            "可以执行 `skillit config probe`，或提高超时：`skillit config set timeout \"120\"`。"
        )
    if reason.startswith("http_error:"):
        code = reason.split(":", 1)[1]
        return (
            f"模型请求返回 HTTP {code}，已切换到离线模式。\n"
            "请执行 `skillit config probe` 查看详细报错。"
        )
    return "当前处于离线模式。"
