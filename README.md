# Aceberg SkillIt (Lightweight)

轻量版 Hermes 风格 Agent Runtime（Python，Skill Pack 结构）：
- 强制 `Plan -> Tool -> Respond`
- 本地会话管理（manifest 指向每个会话的 JSON/JSONL 文件）
- 上下文压缩 + 会话级记忆管理
- 纯标准库，代码量控制在几百行

## 目录

- `skillit/` 核心代码
- `skills/` Skill Pack 目录（`SKILL.md` + `scripts/` + `references/` + `assets/`）
- `sessions/manifest.json` 会话索引
- `sessions/<session_id>/` 会话内容文件
- `docs/ARCHITECTURE.md` 架构说明
- `docs/ARCHITECTURE_DIAGRAMS.md` Mermaid 架构图与时序图
- `docs/SKILL_PACK_DESIGN.md` Skill 架构设计与主流方案对比

## 快速开始

```bash
python -m pip install -e .
skillit --list-skills
skillit --list-tools
skillit --list-sessions
skillit --once "列出当前目录文件"
skillit --new-session
```

设置 `OPENAI_API_KEY` 时调用 OpenAI Responses API；
未设置时自动回退 echo 模式，方便调试执行链路。

推荐做法：在项目根目录创建 `.env`，SkillIt 启动时会自动加载。
可以直接从 `.env.example` 复制：

```bash
cp .env.example .env
```

也可以直接用 CLI 管理配置：

```bash
skillit config set api-key "your-api-key"
skillit config set base-url "https://dashscope.aliyuncs.com/compatible-mode/v1"
skillit config set model "qwen-plus"
skillit config set api-style "chat_completions"
skillit config show
skillit config probe
```

## 对接你自己的 API / Key

LLM 对接代码位置：[llm.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/llm.py)

默认读取这些环境变量：
- `SKILLIT_API_KEY`（优先）或 `OPENAI_API_KEY`
- `SKILLIT_BASE_URL`（默认 `https://api.openai.com/v1`）
- `SKILLIT_MODEL`（默认 `gpt-5.4-mini`）
- `SKILLIT_API_STYLE`：`responses`（默认）或 `chat_completions`
- `SKILLIT_TIMEOUT_SEC`（默认 `60`）

示例 1（OpenAI / Responses）：

```bash
export SKILLIT_API_KEY="你的key"
export SKILLIT_BASE_URL="https://api.openai.com/v1"
export SKILLIT_MODEL="gpt-5.4-mini"
export SKILLIT_API_STYLE="responses"
```

示例 2（OpenAI 兼容网关 / Chat Completions）：

```bash
export SKILLIT_API_KEY="你的key"
export SKILLIT_BASE_URL="https://你的网关域名/v1"
export SKILLIT_MODEL="你的模型名"
export SKILLIT_API_STYLE="chat_completions"
```

验证配置是否生效：

```bash
skillit --health
skillit --health --probe
```

## Skill 格式（Skill Pack）

在 `skills/` 下新建目录：

```text
skills/
  my_skill/
    SKILL.md
    scripts/
      run.py
    references/
      notes.md
    assets/
      .gitkeep
```

`SKILL.md` 示例：

```md
---
id: my_skill
name: MySkill
description: short description
triggers: keyword1,keyword2
---
你的技能提示词正文
```

脚本约定：
- 放在 `skills/<id>/scripts/`
- 支持 `.py/.sh/.js`
- 可通过工具 `run_skill_script` 执行
- 输入通过 `SKILLIT_INPUT_JSON` 传入（JSON 字符串）

资源目录约定：
- `references/`：放 prompt 参考资料、领域说明、模板、规范文档
- `assets/`：放图片、样例数据、静态资源等非脚本文件
- 这两个目录当前不执行，但会被 loader 识别并计入 skill 元数据

内置 skills（当前）：
- `Default`
- `Coding`
- `Planner`
- `FileOps`
- `MemoryManager`

## 内置工具（当前 5 个）

工具实现位置：[tools.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/tools.py)

- `list_files`: 列目录
- `read_text`: 读文件
- `search_text`: 全局搜索
- `write_text`: 写文件（覆盖/追加）
- `run_skill_script`: 运行 skill 包内本地脚本

## 会话文件结构

```text
sessions/
  manifest.json
  s_xxxxx/
    meta.json
    turns.jsonl
    memories.jsonl
    plans.jsonl
    tools.jsonl
```

`manifest.json` 保存 active session 和每个 session 文件指针。

说明：
- 旧版 `memory/memory.jsonl` 已弃用并移除。
- 当前记忆统一按会话存储在 `sessions/<sid>/memories.jsonl`。

## 记忆管理链路（抽取 / 压缩 / 召回）

代码位置：
- 抽取：`skillit/memory.py` 的 `MemoryExtractor.extract()`
- 召回：`skillit/session_store.py` 的 `load_memories()`
- 压缩：`skillit/memory.py` 的 `compact_memories()`
- 注入上下文：`skillit/executor.py` + `skillit/compressor.py`

执行时序（每轮）：
1. 从会话读取 `memories.jsonl`（召回）
2. `compact_memories` 压缩成摘要字符串
3. 摘要注入 prompt 的 `# Retrieved Memory`
4. 对 user/reply 做 `MemoryExtractor.extract`
5. 新记忆追加写回该会话的 `memories.jsonl`

## 运行时流水线

1. 路由 skill
2. 读取 `soul.md`（全局人格约束）+ 会话历史 + 会话记忆
3. 先生成 plan（mandatory）
4. 按 plan 执行多个 tool steps（串行依赖）
5. 压缩上下文并调用 LLM
6. 回写 turns/memories/plans/tools
