# Skill Pack 设计说明（主流方案对比）

这份文档回答两个问题：
1. 为什么要把 `skills/` 从平铺 md 改成目录化 Skill Pack
2. 业界常见方案有哪些，当前项目选了哪种

## 1. 当前采用的方案

采用目录化 Skill Pack：

```text
skills/
  <skill_id>/
    skill.md
    scripts/
      *.py | *.sh | *.js
```

- `skill.md`：声明 skill 元信息与提示词
- `scripts/`：存放可执行脚本（被 `run_skill_script` 调用）

这是一个轻量但实用的中间形态：
- 比“纯 prompt”更能落地动作
- 比“重型插件系统”更容易维护

## 2. 主流方案对比

### 方案 A：Prompt-Only Skill（最轻）

结构：`skills/*.md`

优点：
- 极简
- 学习成本最低

缺点：
- 无法原生挂本地执行能力
- 复杂任务要把执行逻辑塞到主程序

适用：
- 纯问答
- 无工具场景

### 方案 B：Skill Pack（当前方案）

结构：`skill.md + scripts/`

优点：
- 技能定义和执行能力聚合在一起
- 可按 skill 独立迭代与发布
- 仍保持轻量和可读性

缺点：
- 需要脚本协议（输入输出约定）
- 需要运行时做脚本调度

适用：
- 本地自动化
- 中等复杂的 Agent 工程

### 方案 C：Plugin/Tool Server（重型）

结构：每个能力作为插件或远端工具服务（例如 MCP/HTTP tool server）

优点：
- 能力可独立部署
- 多语言/多进程隔离更好
- 适合大团队协作

缺点：
- 研发与运维成本高
- 调试链路长

适用：
- 企业级平台化
- 多团队共享工具生态

## 3. 当前项目的“主流化改造点”

1. `Skill` 数据结构支持 `id/root_dir/scripts`
2. Loader 优先读取目录化 Skill Pack，兼容旧版 flat md
3. ToolRegistry 新增 `run_skill_script`
4. Planner 能规划脚本执行 step（`skill=<id> script=<name>`）
5. 会话日志可记录脚本执行输入与结果

## 4. 脚本调用约定（当前）

调用工具：`run_skill_script`

参数两种方式：
1. `{"skill": "file_ops", "script": "list_tree.py", "input": {...}}`
2. `{"path": "skills/file_ops/scripts/list_tree.py", "input": {...}}`

脚本输入：
- 环境变量 `SKILLIT_INPUT_JSON`
- 同时通过 stdin 传同一份 JSON

脚本输出：
- 推荐输出 JSON 到 stdout
- 运行时会尝试解析 stdout 为 JSON

## 5. 下一步可继续主流化的方向

1. 增加 `skill.yaml`（比 front matter 更结构化）
2. 每个 skill 增加 `tests/`（脚本可测）
3. 增加权限模型（每个 skill 允许访问的路径/tool 白名单）
4. 增加版本字段（skill version + migration）
5. 增加远端工具桥接（本地脚本 + HTTP tool 混用）
