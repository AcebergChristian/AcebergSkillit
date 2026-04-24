# Architecture Diagrams (Mermaid)

下面两张图用于展示 SkillIt 的整体架构与单轮请求流转。

## 1) Overall Architecture

```mermaid
flowchart TB
    U[User]
    CLI[CLI / app.py]
    EX[AgentExecutor]

    SR[SkillRouter]
    PL[Planner]
    TR[ToolRegistry\nlist/read/search/write]
    SS[SessionStore]
    CM[Context Builder / Compressor]
    ME[MemoryExtractor]
    LLM[LLM Client\nresponses/chat_completions]

    SOUL[soul.md]
    SK[skills/*.md]
    SESS[sessions/\nmanifest + jsonl files]

    U --> CLI
    CLI --> EX

    EX --> SR
    SK --> SR

    EX --> SS
    SS <--> SESS

    EX --> PL
    PL --> EX

    EX --> TR
    TR --> EX

    EX --> CM
    SOUL --> CM
    SR --> CM
    SS --> CM
    PL --> CM
    TR --> CM

    CM --> LLM
    LLM --> EX

    EX --> ME
    ME --> SS

    EX --> CLI
    CLI --> U
```

## 2) Single-Turn Runtime Sequence

```mermaid
sequenceDiagram
    participant User
    participant CLI as CLI/app.py
    participant EX as AgentExecutor
    participant SS as SessionStore
    participant SR as SkillRouter
    participant PL as Planner
    participant TR as ToolRegistry
    participant CM as Compressor
    participant LLM as LLM Client
    participant ME as MemoryExtractor

    User->>CLI: input text
    CLI->>EX: run_turn(input, session_id?)

    EX->>SS: ensure(session)
    SS-->>EX: sid

    EX->>SR: route(input, skills)
    SR-->>EX: selected skill

    EX->>SS: load_recent_turns(sid)
    SS-->>EX: recent turns
    EX->>SS: load_memories(sid)
    SS-->>EX: memories

    EX->>PL: build_plan(input, history)
    PL-->>EX: Plan(steps)
    EX->>SS: append_plan(sid, plan)

    loop for each tool step in plan order
        EX->>EX: resolve step input placeholders
        EX->>TR: run(tool, resolved_input)
        TR-->>EX: tool result
        EX->>SS: append_tool_result(sid, payload)
    end

    EX->>CM: build_context(soul + skill + plan + tools + memory + convo + input)
    CM-->>EX: prompt context

    EX->>LLM: generate(context)
    LLM-->>EX: reply

    EX->>SS: append_turn(user)
    EX->>SS: append_turn(assistant)

    EX->>ME: extract(user/reply)
    ME-->>EX: memory items
    EX->>SS: append_memory(items)

    EX-->>CLI: {session_id, plan, tool_results, reply}
    CLI-->>User: render output
```

## 3) Notes

- 计划是强制阶段：每轮都先 `build_plan`，再执行工具步骤。
- 工具步骤支持串行依赖：后一步可引用前一步结果（如 `{{last_search_hit_file}}`）。
- 所有状态可审计：turn/plan/tool/memory 都会落盘到 `sessions/<sid>/`。
