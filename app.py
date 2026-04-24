from skillit.executor import AgentExecutor


def main() -> None:
    agent = AgentExecutor()

    # Create or reuse a session id as needed.
    session_id = agent.create_session("app-demo")
    print("session:", session_id)

    queries = [
        '先搜索 "planner" 再读取内容',
        "帮我查一下文件夹的 ls",
        "帮我列举出有关的py文件"
    ]

    for i, q in enumerate(queries, start=1):
        out = agent.run_turn(q, session_id=session_id)
        print(f"\n--- turn {i} ---")
        print("skill:", out["skill"])
        print("plan steps:")
        for step in out["plan"]["steps"]:
            if step["kind"] == "tool":
                print(
                    f"- {step['id']} [tool] {step.get('tool','')} "
                    f"depends_on={step.get('depends_on', [])} "
                    f"input={step.get('tool_input', {})}"
                )
            else:
                print(f"- {step['id']} [{step['kind']}] {step['description']}")

        print("tool results:", len(out["tool_results"]))
        print("reply:", out["reply"])


if __name__ == "__main__":
    main()
