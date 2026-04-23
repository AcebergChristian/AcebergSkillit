from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(slots=True)
class LLMReply:
    text: str
    model: str


class BaseLLM:
    def generate(self, prompt: str) -> LLMReply:
        raise NotImplementedError


class EchoLLM(BaseLLM):
    """Default offline fallback for local development."""

    def generate(self, prompt: str) -> LLMReply:
        tail = prompt[-700:]
        return LLMReply(text="[echo-mode]\n" + tail, model="echo")


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
            return EchoLLM().generate(prompt)

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
        except urllib.error.URLError:
            return EchoLLM().generate(prompt)

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
