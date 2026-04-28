from __future__ import annotations

import argparse
import itertools
import threading
import time

from .config import CONFIG_ENV_KEYS, get_dotenv_value, resolve_config_key, set_dotenv_value
from .executor import AgentExecutor


def _print_config_help() -> None:
    print("config keys:")
    for alias, env_key in CONFIG_ENV_KEYS.items():
        print(f"- {alias} -> {env_key}")


def _handle_config_command(args: list[str]) -> int:
    if not args:
        print("usage: skillit config <show|get|set|probe> ...")
        _print_config_help()
        return 1

    cmd = args[0]
    if cmd == "show":
        agent = AgentExecutor()
        _print_health(agent, probe=False)
        return 0

    if cmd == "probe":
        agent = AgentExecutor()
        _print_health(agent, probe=True)
        return 0

    if cmd == "get":
        if len(args) != 2:
            print("usage: skillit config get <key>")
            _print_config_help()
            return 1
        try:
            env_key = resolve_config_key(args[1])
        except KeyError:
            print(f"unknown config key: {args[1]}")
            _print_config_help()
            return 1
        value = get_dotenv_value(env_key)
        if not value:
            print(f"{env_key}=(empty)")
        elif "KEY" in env_key:
            print(f"{env_key}=***configured***")
        else:
            print(f"{env_key}={value}")
        return 0

    if cmd == "set":
        if len(args) < 3:
            print("usage: skillit config set <key> <value>")
            _print_config_help()
            return 1
        try:
            env_key = resolve_config_key(args[1])
        except KeyError:
            print(f"unknown config key: {args[1]}")
            _print_config_help()
            return 1
        value = " ".join(args[2:])
        path = set_dotenv_value(env_key, value)
        shown = "***configured***" if "KEY" in env_key else value
        print(f"updated {env_key} in {path}")
        print(f"{env_key}={shown}")
        return 0

    print(f"unknown config command: {cmd}")
    print("usage: skillit config <show|get|set|probe> ...")
    _print_config_help()
    return 1


def _print_health(agent: AgentExecutor, *, probe: bool = False) -> None:
    health = agent.llm.health()
    print("LLM health:")
    print(f"- provider: {health.provider}")
    print(f"- mode: {health.mode}")
    print(f"- model: {health.model}")
    print(f"- api_style: {health.api_style}")
    print(f"- base_url: {health.base_url or '(empty)'}")
    print(f"- endpoint: {health.endpoint or '(empty)'}")
    print(f"- api_key_present: {health.api_key_present}")
    print(f"- api_key: {health.api_key_masked}")
    print(f"- timeout_sec: {health.timeout_sec}")
    if probe:
        print("LLM probe:")
        result = agent.llm.probe()
        print(f"- ok: {result.ok}")
        print(f"- status: {result.status}")
        print(f"- endpoint: {result.endpoint or '(empty)'}")
        print(f"- model: {result.model}")
        print(f"- detail: {result.detail}")


def _print_startup_warning(agent: AgentExecutor) -> None:
    health = agent.llm.health()
    if health.api_key_present:
        return
    print("WARNING: model api key is not configured.")
    print("WARNING: SkillIt will fall back to offline mode and will not return real AI answers.")
    print("WARNING: set `SKILLIT_API_KEY` and verify with `/health --probe`.")


def _print_sessions(agent: AgentExecutor) -> None:
    sessions = agent.list_sessions()
    if not sessions:
        print("(no sessions)")
        return
    for s in sessions:
        mark = "*" if s.get("active") else " "
        print(f"{mark} {s['id']}  {s['title']}  {s['updated_at']}")


def _run_with_spinner(fn, *args, label: str = "thinking", **kwargs):
    stop = threading.Event()

    def spin() -> None:
        for ch in itertools.cycle("|/-\\"):
            if stop.is_set():
                break
            print(f"\r{label} {ch}", end="", flush=True)
            time.sleep(0.1)
        print("\r" + " " * (len(label) + 3) + "\r", end="", flush=True)

    t = threading.Thread(target=spin, daemon=True)
    t.start()
    try:
        return fn(*args, **kwargs)
    finally:
        stop.set()
        t.join(timeout=0.3)


def _print_once_output(out: dict) -> None:
    print(f"session: {out['session_id']}")
    print(f"skill: {out['skill']}")
    print("plan:")
    for step in out["plan"]["steps"]:
        if step["kind"] == "tool":
            dep = f" depends_on={step.get('depends_on', [])}" if step.get("depends_on") else ""
            print(f"- {step['id']} [tool] {step.get('tool', '')}{dep} input={step.get('tool_input', {})}")
        else:
            print(f"- {step['id']} [{step['kind']}] {step['description']}")
    print("reply:")
    print(out["reply"])


def _run_turn_cli(agent: AgentExecutor, text: str, session_id: str | None, label: str) -> dict | None:
    try:
        return _run_with_spinner(agent.run_turn, text, session_id=session_id, label=label)
    except KeyboardInterrupt:
        print("\nrequest interrupted. nothing was sent after cancellation.")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"\nrequest failed: {e}")
        print("tip: run `/health` to inspect current model config.")
        return None


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "config":
        raise SystemExit(_handle_config_command(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="SkillIt tiny runtime")
    parser.add_argument("--once", help="single-turn input")
    parser.add_argument("--list-skills", action="store_true")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--session", help="use specific session id")
    parser.add_argument("--new-session", action="store_true")
    parser.add_argument("--list-sessions", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()

    agent = AgentExecutor()

    if args.list_skills:
        for s in agent.list_skills():
            print(s)
        return

    if args.list_tools:
        for t in agent.list_tools():
            print(f"{t['name']}: {t['desc']}")
        return

    if args.list_sessions:
        _print_sessions(agent)
        return

    if args.health:
        _print_health(agent, probe=args.probe)
        return

    active_session = args.session
    if args.new_session:
        active_session = agent.create_session("interactive")

    if args.once:
        out = _run_turn_cli(agent, args.once, active_session, label="processing")
        if out is not None:
            _print_once_output(out)
        return

    if not active_session:
        active_session = agent.create_session("interactive")

    _print_startup_warning(agent)
    print(f"SkillIt interactive mode. session={active_session}. type /exit to quit")
    print("commands: /new [title], /use <session_id>, /sessions, /health, /health --probe")
    while True:
        try:
            text = input("Aceberg> ").strip()
        except KeyboardInterrupt:
            print("\nexiting on Ctrl+C")
            break
        except EOFError:
            print()
            break
        if not text:
            # print("请输入内容，或输入 /exit 退出。")
            continue
        if text in {"/exit", "/quit"}:
            break
        if text.startswith("/new"):
            title = text.replace("/new", "", 1).strip() or "interactive"
            active_session = agent.create_session(title=title)
            print(f"switched to session: {active_session}")
            continue
        if text.startswith("/use "):
            sid = text.replace("/use ", "", 1).strip()
            active_session = sid
            print(f"switched to session: {active_session}")
            continue
        if text == "/sessions":
            _print_sessions(agent)
            continue
        if text == "/health":
            _print_health(agent, probe=False)
            continue
        if text == "/health --probe":
            _print_health(agent, probe=True)
            continue

        out = _run_turn_cli(agent, text, active_session, label="processing")
        if out is None:
            continue
        active_session = out["session_id"]
        print("bot>", out["reply"])


if __name__ == "__main__":
    main()
