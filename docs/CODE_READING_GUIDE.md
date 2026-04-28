# Aceberg SkillIt 代码共读手册

这份文档是给“接手项目的人”看的完整共读说明，目标是让你从 0 到 1 看懂：
- 这个架子的核心设计是什么
- 一次请求到底怎么跑完
- 每个文件在系统中的角色
- 你后续改功能时该从哪里下手

---

## 1. 项目一句话定位

SkillIt 是一个轻量 Agent Runtime，核心是：
1. 先做任务规划（Plan）
2. 再按计划调工具（Tools）
3. 最后基于上下文生成回复（Respond）

并且具备：
- 会话级本地持久化（sessions 目录）
- 可压缩上下文
- 规则型记忆抽取
- Skill Pack 配置（`SKILL.md` + `scripts/` + `references/` + `assets/`）
- 全局人格注入（soul.md）

---

## 2. 当前代码规模与目录

总代码约 1321 行（包含 `.py` + `.md`）。

关键目录：
- `skillit/`: 运行时核心代码
- `skills/`: Skill Pack 目录（SKILL.md + scripts + references + assets）
- `sessions/`: 会话索引与会话数据
- `soul.md`: 全局人格
- `app.py`: import 方式最小示例
- `README.md`: 使用说明
- `docs/ARCHITECTURE.md`: 架构简版说明

---

## 3. 推荐阅读顺序（强烈建议按这个来）

1. `skillit/cli.py`
2. `skillit/executor.py`
3. `skillit/planner.py`
4. `skillit/tools.py`
5. `skillit/session_store.py`
6. `skillit/compressor.py`
7. `skillit/memory.py`
8. `skillit/llm.py`
9. `skillit/schema.py`
10. `skills/<skill_id>/SKILL.md` + `skills/<skill_id>/scripts/*` + `skills/<skill_id>/references/*` + `skills/<skill_id>/assets/*` + `soul.md`

原因：这是最符合真实调用链的顺序。

---

## 4. 运行时总流程（按调用顺序）

入口通常是 CLI：`skillit/cli.py`。

单轮 `run_turn()` 执行顺序（`skillit/executor.py`）：
1. `SessionStore.ensure()` 选定/恢复会话
2. `SkillRouter.route()` 根据 `triggers` 选 skill
3. 加载最近会话 turns 与会话 memories
4. `Planner.build_plan()` 生成计划（必须）
5. 遍历计划中的 `tool` step，顺序执行工具
6. 拼装 plan/tool/memory/conversation/soul 到 context
7. 调 LLM（OpenAI 或兼容接口）
8. 回写 turns
9. 从 user/reply 文本抽取 memory 并回写
10. 返回结构化结果（session_id / plan / tool_results / reply）

---

## 5. 模块级详解

### 5.1 `skillit/cli.py`

职责：命令行入口 + 交互循环 + loading spinner。

支持参数：
- `--once`
- `--list-skills`
- `--list-tools`
- `--list-sessions`
- `--session`
- `--new-session`

交互命令：
- `/new [title]`
- `/use <session_id>`
- `/sessions`
- `/exit`

关键点：
- `_run_with_spinner()` 用线程打印 loading（`|/-\\`）。
- 无论 `--once` 还是交互，都调用 `AgentExecutor.run_turn()`。

---

### 5.2 `skillit/executor.py`

这是系统中最核心的编排器（orchestrator）。

主要对象：
- `SkillRouter`
- `SessionStore`
- `Planner`
- `ToolRegistry`
- `MemoryExtractor`
- `OpenAIResponsesLLM`

`run_turn()` 关键逻辑：
1. 会话与 skill 决策
2. 生成 plan
3. 执行多个 tool step
4. 处理 step 依赖输入（`_resolve_tool_input`）
5. 构建最终 context 并调用模型
6. 记日志、记忆回写

依赖注入能力：
- 支持 `{{last_search_hit_file}}`
- 支持通用路径变量：`{{s2.result.data.hits.0.file}}`

这意味着可以“前一步搜索 -> 后一步读取”自动串起来。

---

### 5.3 `skillit/planner.py`

职责：把自然语言请求转成执行计划（Plan）。

核心策略：
- 关键词启发式匹配操作类型：
  - `list_files`
  - `read_text`
  - `search_text`
  - `write_text`
- 先固定 `s1 analyze`
- 再生成 0~N 个 `tool` step
- 最后固定 `respond`

依赖处理：
- tool steps 默认串行依赖前一步（`depends_on=[prev_step]`）
- 如果出现“先搜索再读取”，读取路径会用 `{{last_search_hit_file}}`

注意：当前是“规则规划器”，不是 LLM 规划器。

---

### 5.4 `skillit/tools.py`

职责：内置工具注册与执行。

内置五工具：
1. `list_files`
2. `read_text`
3. `search_text`
4. `write_text`
5. `run_skill_script`

安全边界：
- `_safe_path()` 限定路径在 workspace 根目录内。

返回格式统一：
- 成功：`{"ok": true, "data": ...}`
- 失败：`{"ok": false, "error": ...}`

---

### 5.5 `skillit/session_store.py`

职责：会话持久化与索引管理。

组织方式：
- `sessions/manifest.json` 维护 active session + 每个 session 文件指针
- 每个 session 一个目录

每会话文件：
- `meta.json`
- `turns.jsonl`
- `memories.jsonl`
- `plans.jsonl`
- `tools.jsonl`

读取策略：
- `load_recent_turns(n)` 取最近 N 条
- `load_memories(max_items)` 取末尾 max_items 条

---

### 5.6 `skillit/compressor.py`

职责：把多来源信息压缩到一个 prompt 字符串。

上下文段顺序：
1. `# Soul`
2. `# System Skill`
3. `# Plan (Must Follow)`
4. `# Tool Results`
5. `# Retrieved Memory`
6. `# Conversation`
7. `# New User Input`

超长时处理：
- 优先裁工具摘要、记忆摘要、旧会话
- 最后硬切到 `max_chars`

---

### 5.7 `skillit/memory.py`

职责：记忆抽取与记忆摘要。

抽取器 `MemoryExtractor`：
- preference 正则
- task 正则
- 兜底 fact（短文本）

压缩函数 `compact_memories()`：
- 按 `score + ts` 排序
- 在字符预算内拼接高价值记忆

---

### 5.8 `skillit/llm.py`

职责：模型调用层（标准库 urllib 实现）。

可配环境变量：
- `SKILLIT_API_KEY` / `OPENAI_API_KEY`
- `SKILLIT_BASE_URL`
- `SKILLIT_MODEL`
- `SKILLIT_API_STYLE` (`responses` / `chat_completions`)
- `SKILLIT_TIMEOUT_SEC`

降级策略：
- 无 key 或网络异常 -> `EchoLLM`

---

### 5.9 `skillit/schema.py`

职责：核心数据结构。

包含 dataclass：
- `Turn`
- `MemoryItem`
- `Skill`
- `PlanStep`
- `Plan`

全部是轻量结构，没有引入外部序列化框架。

---

### 5.10 `skillit/skill_loader.py`

职责：加载 Skill Pack（目录）与兼容旧版 flat md。

行为：
- 优先读取 `skills/<skill_id>/SKILL.md`，兼容读取 `skills/<skill_id>/skill.md` 与 `skills/*.md`
- 解析 front matter (`name/description/triggers`)
- 生成 `Skill` 列表

---

### 5.11 `skillit/config.py`

职责：运行时配置集中定义。

当前关键配置：
- `skills_dir`
- `sessions_dir`
- `soul_file`
- `short_term_turns`
- `max_context_chars`
- `max_memory_items`
- `max_tool_output_chars`

---

## 6. Skills 与 Soul 的角色边界

### Skills (`skills/<skill_id>/SKILL.md`)

用途：
- 任务域内行为约束（比如 coding、file ops）
- 通过 trigger 决定被路由选中

当前内置：
- `Default`
- `Coding`
- `Planner`
- `FileOps`
- `MemoryManager`

### Soul (`soul.md`)

用途：
- 全局人格层，不随具体 skill 切换
- 每轮对话都会注入 context

简单理解：
- soul = “这个 agent 始终是谁”
- skill = “这轮任务用什么工作模式”

---

## 7. 会话数据格式（你排查问题最常看的地方）

### `sessions/manifest.json`

作用：
- 记录 `active_session`
- 记录每个 session 的文件路径指针

### `turns.jsonl`

每行一条：
- `role`
- `content`
- `ts`

### `plans.jsonl`

每行一轮计划：
- `goal`
- `steps[]`
- `ts`

### `tools.jsonl`

每行一次工具调用：
- `step_id`
- `depends_on`
- `tool`
- `planned_input`
- `input`（解析变量后）
- `result`

### `memories.jsonl`

每行一条记忆：
- `kind`
- `content`
- `score`
- `ts`

---

## 8. 一次完整请求的时序例子

用户输入：`先搜索 "planner" 再读取内容`

Planner 产出（示意）：
1. `s1 analyze`
2. `s2 tool search_text(path='.', pattern='planner')`
3. `s3 tool read_text(path='{{last_search_hit_file}}', depends_on=['s2'])`
4. `s4 respond`

执行器行为：
1. 先执行 `s2`
2. `s2` 结果命中若干文件
3. 执行 `s3` 前把 `{{last_search_hit_file}}` 解析成真实路径
4. 把 tools 结果写入 `tools.jsonl`
5. 拼接 context 调模型
6. 写入 turns + memories

---

## 9. 为什么这个架子是“轻量但完整”

轻量：
- 标准库实现，无重依赖
- 规则式 planner/memory
- 文件型存储，无数据库

完整：
- 有规划
- 有工具
- 有会话
- 有记忆
- 有上下文压缩
- 有人格注入
- 有 CLI + import 双入口

---

## 10. 你接手后最常改的点

1. 改规划能力：`skillit/planner.py`
2. 增工具：`skillit/tools.py`
3. 调上下文拼装顺序：`skillit/compressor.py`
4. 优化记忆抽取：`skillit/memory.py`
5. 替换模型协议：`skillit/llm.py`
6. 调 skill 路由策略：`skillit/executor.py` 的 `SkillRouter`

---

## 11. 当前实现的已知边界（你需要心里有数）

1. Planner 是关键词启发式，不理解复杂语义。
2. `depends_on` 目前是线性链，不是 DAG 调度器。
3. 变量解析能力有限，复杂模板需要扩展 `_resolve_tool_input()`。
4. 记忆抽取是规则法，容易漏掉隐式偏好。
5. prompt 长度目前按字符截断，不是 token 精确预算。
6. 默认工具是本地文件工具，暂无 HTTP/DB 等外部工具。

---

## 12. 本地调试建议

### 12.1 快速查看能力

```bash
skillit --list-skills
skillit --list-tools
skillit --list-sessions
```

### 12.2 跑一轮并看落盘

```bash
skillit --once '先搜索 "planner" 再读取内容'
```

然后检查：
- `sessions/manifest.json`
- 对应 session 的 `plans.jsonl` / `tools.jsonl` / `turns.jsonl`

### 12.3 Python import 方式

参考：`app.py`

---

## 13. 这份架子最关键的 3 个心智模型

1. **编排优先**：`AgentExecutor` 是中控，其他模块都围绕它服务。
2. **文件即状态**：会话状态不是内存黑盒，是可审计的 JSON/JSONL。
3. **约束外置**：人格和技能尽量写在 Markdown，不把策略硬编码到 Python。

---

## 14. 30 分钟上手计划（给你自己或团队新人）

1. 先读 `executor.py` + `planner.py`（10 分钟）
2. 跑一次 CLI，观察 `sessions/*` 文件变化（10 分钟）
3. 新增一个 skill、改一条 planner 规则并验证（10 分钟）

做到这 3 步，就能真正掌控这个项目。
