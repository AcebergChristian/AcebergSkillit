# Aceberg SkillIt (Lightweight)

轻量版 Hermes 风格 Agent Runtime（Python，平铺 skills）：
- 强制 `Plan -> Tool -> Respond`
- 本地会话管理（manifest 指向每个会话的 JSON/JSONL 文件）
- 上下文压缩 + 会话级记忆管理
- 纯标准库，代码量控制在几百行

## 目录

- `skillit/` 核心代码
- `skills/` 平铺 skill 文件（Markdown + front matter）
- `sessions/manifest.json` 会话索引
- `sessions/<session_id>/` 会话内容文件
- `docs/ARCHITECTURE.md` 架构说明
- `docs/ARCHITECTURE_DIAGRAMS.md` Mermaid 架构图与时序图

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

## Skill 格式（平铺）

在 `skills/` 下新建 `xxx.md`：

```md
---
name: MySkill
description: short description
triggers: keyword1,keyword2
---
你的技能提示词正文
```

内置 skills（当前）：
- `Default`
- `Coding`
- `Planner`
- `FileOps`
- `MemoryManager`

## 内置工具（Hermes 风格 4 个）

工具实现位置：[tools.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/tools.py)

- `list_files`: 列目录
- `read_text`: 读文件
- `search_text`: 全局搜索
- `write_text`: 写文件（覆盖/追加）

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

## 运行时流水线

1. 路由 skill
2. 读取 `soul.md`（全局人格约束）+ 会话历史 + 会话记忆
3. 先生成 plan（mandatory）
4. 按 plan 执行多个 tool steps（串行依赖）
5. 压缩上下文并调用 LLM
6. 回写 turns/memories/plans/tools
