from __future__ import annotations

import argparse
import itertools
import threading
import time

from .executor import AgentExecutor


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


def main() -> None:
    parser = argparse.ArgumentParser(description="SkillIt tiny runtime")
    parser.add_argument("--once", help="single-turn input")
    parser.add_argument("--list-skills", action="store_true")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--session", help="use specific session id")
    parser.add_argument("--new-session", action="store_true")
    parser.add_argument("--list-sessions", action="store_true")
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

    active_session = args.session
    if args.new_session:
        active_session = agent.create_session("interactive")

    if args.once:
        out = _run_with_spinner(agent.run_turn, args.once, session_id=active_session, label="processing")
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
        return

    if not active_session:
        active_session = agent.create_session("interactive")

    print(f"SkillIt interactive mode. session={active_session}. type /exit to quit")
    print("commands: /new [title], /use <session_id>, /sessions")
    while True:
        try:
            text = input("Aceberg> ").strip()
        except EOFError:
            print()
            break
        if not text:
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

        out = _run_with_spinner(agent.run_turn, text, session_id=active_session, label="processing")
        active_session = out["session_id"]
        print("bot>", out["reply"])


if __name__ == "__main__":
    main()
