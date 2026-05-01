# AcebergSkillit 项目树说明

本文档说明当前项目的目录结构、核心文件职责，以及运行时生成目录的含义。

## 1. 顶层结构

```text
AcebergSkillit/
├── .env
├── .env.example
├── .gitignore
├── README.md
├── api.py
├── app.py
├── main.py
├── pyproject.toml
├── soul.md
├── output.txt
├── PROJECT_TREE_EXPLAINED.md
├── aceberg_skillit.egg-info/
├── demo_pic/
├── docs/
├── output/
├── sessions/
├── skillit/
├── skills/
└── web/
```

## 2. 顶层文件说明

- `.env`
  本地运行时环境变量配置，通常放 API Key、模型地址、超时等敏感配置。

- `.env.example`
  `.env` 的示例模板，告诉你支持哪些环境变量。

- `.gitignore`
  Git 忽略规则，避免提交缓存、产物、敏感文件等。

- `README.md`
  项目主说明文档，介绍功能、运行方式、命令入口。

- `api.py`
  FastAPI 路由层。对前端暴露 `/api/runtime`、`/api/sessions`、`/api/chat/stream` 等接口。

- `app.py`
  一个本地调试/脚本式入口，通常用于手工调用 `AgentExecutor` 做实验。

- `main.py`
  FastAPI 应用入口，创建 `app = FastAPI(...)`，用于启动后端服务。

- `pyproject.toml`
  Python 项目配置文件，包含包信息、依赖、CLI 入口等。

- `soul.md`
  Agent 的系统人格/执行规则提示词。运行时会被拼进 prompt。

- `output.txt`
  一个普通输出文件，像调试产物或历史测试残留，不是核心代码文件。

- `PROJECT_TREE_EXPLAINED.md`
  当前这份项目结构说明文档。

## 3. `aceberg_skillit.egg-info/`

这是 Python 打包安装后自动生成的元数据目录。

包含：

- `PKG-INFO`
  包元信息。

- `SOURCES.txt`
  打包时纳入的文件清单。

- `dependency_links.txt`
  依赖链接信息。

- `entry_points.txt`
  CLI 入口点定义。

- `top_level.txt`
  顶层包名信息。

这整个目录基本不需要手改。

## 4. `demo_pic/`

```text
demo_pic/
├── WX20260430-185714@2x.png
├── WX20260430-190109@2x.png
├── WX20260430-190120@2x.png
└── WX20260430-190150@2x.png
```

用途：
- 存放项目界面或流程演示截图。
- 主要用于人工查看、给 UI 调整做参考。

## 5. `docs/`

```text
docs/
├── ARCHITECTURE.md
├── ARCHITECTURE_DIAGRAMS.md
├── CODE_READING_GUIDE.md
├── SKILL_PACK_DESIGN.md
├── flow_chart.png
└── sequence_diagram.png
```

文件说明：

- `ARCHITECTURE.md`
  项目整体架构说明。

- `ARCHITECTURE_DIAGRAMS.md`
  配合文字说明的架构图/时序图版本。

- `CODE_READING_GUIDE.md`
  帮人快速读代码的导览文档。

- `SKILL_PACK_DESIGN.md`
  `skills/` 目录这套 Skill Pack 结构设计说明。

- `flow_chart.png`
  流程图图片。

- `sequence_diagram.png`
  时序图图片。

## 6. `skillit/` 核心后端包

```text
skillit/
├── __init__.py
├── cli.py
├── compressor.py
├── config.py
├── executor.py
├── llm.py
├── memory.py
├── planner.py
├── schema.py
├── session_store.py
├── skill_loader.py
└── tools.py
```

### `skillit/__init__.py`
- 包导出入口。
- 暴露 `AgentExecutor`、`RuntimeConfig` 给外部调用。

### `skillit/cli.py`
- 命令行入口实现。
- 负责 `skillit ...` 这类 CLI 命令。

### `skillit/compressor.py`
- 负责拼 prompt。
- 把 soul、skill、plan、tool results、memory、conversation、new input 组装成模型输入。

核心方法：
- `build_context(...)`

### `skillit/config.py`
- 运行时配置对象。
- 负责读取 `.env` 和环境变量。

常见配置包括：
- 模型名
- base_url
- api_key
- 超时
- output 目录
- short-term turns 数量

### `skillit/executor.py`
- 项目最核心的执行器。
- 协调整轮对话：会话、规划、工具、模型、自动写文件、自动执行、事件流。

核心职责：
- 创建任务输出目录
- 读取历史 turns / tools / memories
- build workflow
- build plan
- run tools
- 组 prompt 调模型
- 自动把生成内容写文件
- 自动执行脚本
- 产出 event / final reply

核心方法：
- `run_turn(...)`
- `run_requirement(...)`
- `create_task_output_dir(...)`
- `_maybe_autosave_generated_file(...)`
- `_maybe_autorun_generated_file(...)`
- `_maybe_execute_embedded_tool_blocks(...)`
- `_event_from_tool_payload(...)`
- `get_session_snapshot(...)`

### `skillit/llm.py`
- 模型适配层。
- 当前支持：
  - `EchoLLM`：离线回退
  - `OpenAIResponsesLLM`：调用在线模型

核心职责：
- 发起模型请求
- 做 health/probe
- 失败时回退离线模式

### `skillit/memory.py`
- 记忆相关逻辑。
- 当前不是“真正抽取字段”，而是规则打标 + 原句入库。

核心内容：
- `MemoryExtractor`
- `compact_memories(...)`

### `skillit/planner.py`
- 规划器。
- 根据用户输入推断：
  - workflow tasks
  - tool plan

核心方法：
- `build_workflow(...)`
- `build_plan(...)`

### `skillit/schema.py`
- 数据结构定义。
- 统一了 Turn、MemoryItem、Skill、WorkflowTask、PlanStep 等 dataclass。

核心类：
- `Turn`
- `MemoryItem`
- `Skill`
- `WorkflowTask`
- `WorkflowPlan`
- `PlanStep`
- `Plan`

### `skillit/session_store.py`
- 会话持久化层。
- 用 json/jsonl 存储 session 元数据、turns、memories、plans、tools、events。

核心方法：
- `create(...)`
- `append_turn(...)`
- `append_memory(...)`
- `append_plan(...)`
- `append_tool_result(...)`
- `append_event(...)`
- `load_recent_turns(...)`
- `load_memories(...)`
- `load_recent_events(...)`

### `skillit/skill_loader.py`
- 加载 `skills/` 目录里的 Skill 包。
- 把 `SKILL.md`、scripts、references、assets 组装成 `Skill` 对象。

### `skillit/tools.py`
- 本地工具注册中心。
- 提供对文件系统和本地脚本的标准化调用。

支持工具：
- `list_files`
- `read_text`
- `search_text`
- `write_text`
- `run_local_script`
- `run_skill_script`

## 7. `skills/` Skill Pack 目录

```text
skills/
├── coding/
├── data_export/
├── default/
├── file_ops/
├── memory_manager/
├── planner/
└── research/
```

每个 skill 目录结构基本一致：

```text
skills/<skill_name>/
├── SKILL.md
├── assets/
├── references/
└── scripts/
```

通用含义：
- `SKILL.md`
  这个 skill 的说明和行为规则，是 prompt 的主要来源。

- `assets/`
  skill 相关静态资源目录，目前大多只有 `.gitkeep`。

- `references/`
  skill 的参考资料目录，目前大多是占位。

- `scripts/`
  该 skill 可运行脚本目录。

### 各 skill 说明

- `skills/coding/`
  编码类任务 skill。
  - `SKILL.md`：告诉模型如何生成/修复代码。
  - `scripts/summarize_patch.py`：和补丁摘要相关的小脚本。

- `skills/data_export/`
  导出数据类 skill，例如 xlsx/csv/json 产物相关。

- `skills/default/`
  默认兜底 skill，用户请求不明显命中特定 skill 时使用。

- `skills/file_ops/`
  文件操作类 skill。
  - `scripts/list_tree.py`：列目录树的小脚本。

- `skills/memory_manager/`
  记忆管理相关 skill，目前更多是提示词层设计。

- `skills/planner/`
  规划相关 skill，用于补充 workflow / plan 行为。

- `skills/research/`
  调研类 skill，面向外部信息收集或结构化研究场景。

## 8. `sessions/` 运行时会话数据

```text
sessions/
├── manifest.json
├── .gitkeep
└── s_<session_id>/
    ├── meta.json
    ├── turns.jsonl
    ├── memories.jsonl
    ├── plans.jsonl
    ├── tools.jsonl
    └── events.jsonl
```

这是运行时最关键的数据目录之一。

### `sessions/manifest.json`
- 全局 session 清单。
- 记录当前 active session，以及各 session 的文件路径。

### `sessions/.gitkeep`
- 占位文件，确保空目录能被 Git 跟踪。

### `sessions/s_<session_id>/`
- 单个会话的持久化目录。

每个会话目录下文件说明：

- `meta.json`
  会话元信息：
  - id
  - title
  - created_at
  - updated_at

- `turns.jsonl`
  原始用户/assistant 对话记录。

- `memories.jsonl`
  “打标后的原句记忆”。

- `plans.jsonl`
  每轮规划结果。

- `tools.jsonl`
  工具调用结果。

- `events.jsonl`
  前端流式显示用的过程事件。

## 9. `output/` 运行产物目录

```text
output/
└── s_<session_id>/
    ├── promotion_candidate.json
    └── YYYYMMDD_HHMMSS/
        ├── generated_script.py
        ├── generated_script.md
        ├── zhihu_analysis.md
        ├── wellfound_report.html
        └── sina_news_today.xlsx
```

这是“执行生成结果”的目录，不是会话元数据。

结构含义：

- `output/s_<session_id>/`
  这个 session 产生的所有文件输出根目录。

- `promotion_candidate.json`
  某些执行结果会被整理成一个潜在可沉淀为 skill 的候选描述。

- `YYYYMMDD_HHMMSS/`
  单次任务执行输出目录。

里面的文件类型示例：
- `generated_script.py`
  生成的 Python 脚本
- `generated_script.md`
  生成的 Markdown 文件
- `zhihu_analysis.md`
  Markdown 报告
- `wellfound_report.html`
  HTML 报告
- `sina_news_today.xlsx`
  Excel 结果文件

说明：
- `output/` 下目录很多，属于历史运行残留。
- 这些目录不是代码模块，而是“曾经跑过的任务产物”。

## 10. `web/` 前端项目

```text
web/
├── index.html
├── package.json
├── package-lock.json
├── postcss.config.js
├── tailwind.config.js
├── vite.config.js
├── public/
├── src/
├── dist/
└── node_modules/
```

### 顶层配置

- `web/index.html`
  Vite 前端入口 HTML。

- `web/package.json`
  前端依赖和 scripts 定义。

- `web/package-lock.json`
  npm 锁文件。

- `web/postcss.config.js`
  PostCSS 配置。

- `web/tailwind.config.js`
  Tailwind 配置。

- `web/vite.config.js`
  Vite 配置。

### `web/public/`
- 静态资源目录。
- 当前基本为空。

### `web/dist/`
- 前端构建产物目录。
- `npm run build` 后生成。

### `web/node_modules/`
- 前端依赖安装目录。
- 全部是第三方依赖，不属于项目源码。

## 11. `web/src/` 前端源码

```text
web/src/
├── App.jsx
├── main.jsx
├── styles.css
├── components/
├── data/
├── lib/
└── pages/
```

### `web/src/main.jsx`
- React 挂载入口。

### `web/src/App.jsx`
- 前端主应用。
- 负责：
  - 暗黑/亮色主题
  - 路由路径切换 `/dash /sessions /skills`
  - 页面容器结构

### `web/src/styles.css`
- 全局样式。
- Tailwind 基础层 + 一些自定义滚动条/视觉规则。

### `web/src/components/`

```text
web/src/components/
├── Icons.jsx
├── Sidebar.jsx
└── TopBar.jsx
```

- `Icons.jsx`
  SVG 图标组件集合。

- `Sidebar.jsx`
  左侧导航栏。

- `TopBar.jsx`
  顶部栏，显示主题切换和 runtime 信息。

### `web/src/data/`

```text
web/src/data/
└── mockData.js
```

- `mockData.js`
  mock 数据，给前端开发调试用。

### `web/src/lib/`

```text
web/src/lib/
└── api.js
```

- `api.js`
  前端 API 调用封装。
  包括：
  - `getOverview()`
  - `getRuntime()`
  - `getSessions()`
  - `getSession()`
  - `getSkills()`
  - `chatStream()` 等

### `web/src/pages/`

```text
web/src/pages/
├── DashPage.jsx
├── SessionsPage.jsx
└── SkillsPage.jsx
```

- `DashPage.jsx`
  仪表盘页，展示 active session 和 recent events。

- `SessionsPage.jsx`
  当前最复杂的页面。
  负责：
  - 会话聊天显示
  - 流式执行过程
  - assistant steps 展示
  - 会话切换
  - 右侧概览/产物/日志

- `SkillsPage.jsx`
  Skill 管理页，展示已加载的 skill 信息。

## 12. 这个项目的“运行时数据”和“源码”怎么区分

### 源码目录
- `skillit/`
- `skills/`
- `web/src/`
- `api.py`
- `main.py`
- `app.py`
- `README.md`
- `docs/`

### 运行时数据目录
- `sessions/`
- `output/`

### 构建/安装目录
- `web/node_modules/`
- `web/dist/`
- `aceberg_skillit.egg-info/`
- `__pycache__/`

## 13. 最核心的 10 个文件

如果你只想抓主线，优先看这 10 个：

1. [main.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/main.py)
2. [api.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/api.py)
3. [skillit/executor.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/executor.py)
4. [skillit/planner.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/planner.py)
5. [skillit/tools.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/tools.py)
6. [skillit/session_store.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/session_store.py)
7. [skillit/memory.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/memory.py)
8. [skillit/llm.py](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/skillit/llm.py)
9. [web/src/App.jsx](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/web/src/App.jsx)
10. [web/src/pages/SessionsPage.jsx](/Users/Aceberg/Desktop/MySelf_Dev/AcebergSkillit/web/src/pages/SessionsPage.jsx)

## 14. 一句话总结

这个项目本质上是一个：

- Python 后端 Agent Runtime
- 带 session/memory/tool/event 持久化
- Skill Pack 可插拔
- React 前端可视化操作台

的轻量工程化 Agent 项目。
