# 架构说明（轻量 Hermes 风格）

## 1. 强制执行链路

每轮固定流程：

1. `SkillRouter` 选 skill
2. 加载 `soul.md` + `SessionStore` 读取会话 turns + memories
3. `Planner` 先产出 plan（至少 analyze/respond）
4. plan 中含多个 tool steps 时，`ToolRegistry` 串行执行（支持依赖前一步输出）
5. `build_context` 压缩会话、记忆、工具结果
6. `LLM.generate` 生成回复
7. 回写 `turns/memories/plans/tools`

核心点：**永远先规划，再工具执行，再回答**。

## 2. 会话管理（本地 IO）

- 索引文件：`sessions/manifest.json`
- 每个会话一个目录：`sessions/<id>/`
- 指向和内容分离：manifest 里存每个会话的文件路径指针

每会话文件：

- `meta.json`：id/title/create/update
- `turns.jsonl`：消息历史
- `memories.jsonl`：抽取记忆
- `plans.jsonl`：每轮计划
- `tools.jsonl`：工具执行记录

## 3. 组件职责

- `planner.py`：计划生成
- `tools.py`：内置工具注册与执行（4 tools: list/read/search/write）
- `session_store.py`：会话索引、读写、切换
- `executor.py`：流水线编排
- `compressor.py`：上下文压缩
- `memory.py`：记忆抽取与压缩

## 4. 轻量设计原则

- skill 行为约束放到 `skills/*.md`
- 运行时只做必要编排，不做重型 workflow engine
- 默认标准库，避免依赖膨胀
