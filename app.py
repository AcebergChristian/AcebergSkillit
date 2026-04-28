from __future__ import annotations

from skillit.executor import AgentExecutor


def print_event(event: dict) -> None:
    et = event.get("type")
    if et == "session":
        print(f"[session] {event.get('message')}")
    elif et == "task_dir":
        print(f"[task_dir] {event.get('task_dir')}")
    elif et == "workflow":
        workflow = event.get("workflow", {})
        print(f"[workflow] primary={workflow.get('primary_skill_id')} goal={workflow.get('goal')}")
        for task in workflow.get("tasks", []):
            print(f"  - {task.get('id')} [{task.get('kind')}] skill={task.get('skill_id') or '-'}")
    elif et == "skill":
        print(f"[skill] {event.get('message')}")
    elif et == "plan":
        print("[plan]")
        for step in event.get("plan", {}).get("steps", []):
            if step.get("kind") == "tool":
                print(f"  - {step.get('id')} tool={step.get('tool')} input={step.get('tool_input')}")
            else:
                print(f"  - {step.get('id')} {step.get('kind')} {step.get('description')}")
    elif et == "tool":
        msg = f"[tool] {event.get('step_id')} {event.get('tool')} ok={event.get('ok')}"
        if event.get("path"):
            msg += f" path={event.get('path')}"
        if event.get("script"):
            msg += f" script={event.get('script')}"
        if event.get("exit_code") is not None:
            msg += f" exit_code={event.get('exit_code')}"
        print(msg)
    elif et == "run":
        print(f"[run] path={event.get('path')} exit_code={event.get('exit_code')}")
    elif et == "repair":
        print(f"[repair] attempt={event.get('attempt')} exit_code={event.get('exit_code')} script={event.get('script')}")
    elif et == "promotion_candidate":
        cand = event.get("candidate", {})
        print(f"[promotion] pending skill_id={cand.get('suggested_skill_id')} script={cand.get('script_path')}")


def print_result(out: dict) -> None:
    print("session:", out["session_id"])
    print("skill:", out["skill"])
    print("task_output_dir:", out.get("task_output_dir", ""))

    workflow = out.get("workflow") or {}
    if workflow:
        print("\nworkflow:")
        print("goal:", workflow.get("goal", ""))
        print("primary_skill:", workflow.get("primary_skill_id", ""))
        for task in workflow.get("tasks", []):
            dep = f" depends_on={task.get('depends_on', [])}" if task.get("depends_on") else ""
            skill = f" skill={task.get('skill_id')}" if task.get("skill_id") else ""
            print(f"- {task.get('id')} [{task.get('kind')}]{skill}{dep} -> {task.get('description')}")

    print("\nplan:")
    for step in out["plan"]["steps"]:
        if step["kind"] == "tool":
            dep = f" depends_on={step.get('depends_on', [])}" if step.get("depends_on") else ""
            print(f"- {step['id']} [tool] {step.get('tool', '')}{dep} input={step.get('tool_input', {})}")
        else:
            print(f"- {step['id']} [{step['kind']}] {step['description']}")

    if out.get("tool_results"):
        print("\ntrace:")
        for item in out["tool_results"]:
            result = item.get("result", {}) or {}
            print(f"- {item.get('step_id')} {item.get('tool')} ok={result.get('ok')}")
            data = result.get("data", {}) if isinstance(result, dict) else {}
            if isinstance(data, dict):
                if data.get("path"):
                    print("  path:", data["path"])
                if data.get("script"):
                    print("  script:", data["script"])
                if data.get("exit_code") is not None:
                    print("  exit_code:", data["exit_code"])

    print("\nreply:")
    print(out["reply"])
    if out.get("promotion_candidate"):
        print("\npromotion_candidate:")
        print(out["promotion_candidate"])


def main() -> None:
    agent = AgentExecutor()
    session_title = "import-runtime-demo"
    # requirement = "帮我分析一下这个网站 https://wellfound.com/startups/location/silicon-valley 需要具体数据清单**（如：列出前 20 家公司的名称、融资轮次、职位数），请授权我使用网络抓取工具执行"
    # requirement = "同意，我将立即生成并执行抓取脚本，写入当前工作目录，并在完成后生成html的报告结果"
    # requirement = "不用selenium呢，就用requests可以么"
    requirement = "没看到  CSV 和 HTML"
    out = agent.run_requirement(
        requirement,
        title=session_title,
        event_callback=print_event,
        reuse_session_by_title=True,
    )
    print_result(out)


if __name__ == "__main__":
    main()
