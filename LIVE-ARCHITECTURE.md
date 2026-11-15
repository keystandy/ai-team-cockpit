# AI 团队真实控制面架构

## 定位

驾驶舱负责人机交互，Python 控制面负责状态与调度，四个引擎 Adapter 负责实际执行。

```text
浏览器驾驶舱
  → Task API (127.0.0.1:8765)
  → Orchestrator
  → SQLite
  → Agent Adapter
  → 独立 Workspace
  → Artifact Store
  → 独立复核
  → 老板终验
```

## 四个平面

| 平面 | 责任 | 当前实现 |
|---|---|---|
| 体验平面 | 输入目标、查看状态、证据与成果 | 现有单页驾驶舱 |
| 控制平面 | DAG、状态、重试、验收、取消 | `server/orchestrator.py` |
| 执行平面 | 调用 DSH、Codex、Claude、豆包 | `server/adapters.py` |
| 状态与证据平面 | 任务、事件、产物、哈希 | `server/store.py` |

## 任务图

确定性 Planner 当前支持三类任务：

```text
分析：小深分析 → 小克复核
检索：小豆检索 → 小深分析 → 小克复核
工程：小深规划 → 小酷实现 → 小克复核
```

任务之间的依赖使用标题引用，结果通过 SQLite 和产物文件传递，不通过自由聊天传递。

## 状态机

```text
waiting
  → running
  → accepted（中间任务通过证据门，或老板终验通过）

running
  → pending_review（复核任务等待老板终验）
  → failed（达到重试上限或引擎失败）

pending_review
  → accepted（仅复核首行为 PASS，且老板确认）

needs_decision
  → accept_shortfall（接受缺口，进入复核）
  → expand_scope（扩大检索窗口，整条链重做）
  → cancel（取消任务）

复核 RETURN
  → 复核任务回到 waiting
  → 上游生产者回到 waiting
  → 自动进行下一轮修正与复核
```

人工不能验收首行不是 `PASS` 的复核任务。

## Adapter 契约

所有员工统一实现：

```text
run(agent_id, prompt, workspace, artifact_path) -> AgentResult
```

引擎差异被封装在 Adapter 内，Orchestrator 不依赖具体 CLI 参数。

当前 Adapter：

- 小深：DSH headless，禁用文件/终端依赖，规划阶段直接接收上下文摘要。
- 小酷：Codex CLI，优先 `workspace-write`，单任务工作目录隔离。
- 小克：Claude Code，`plan` 模式并禁用工具，只审查传入证据。
- 小豆：豆包桥接，检索任务可开启联网。

## 安全边界

- 服务只监听 `127.0.0.1`。
- 目标工作区只能位于 `cockpit/workspaces`。
- 静态服务禁止访问 `server/`、`runtime/`、`workspaces/` 和 SQLite。
- API 不允许客户端传入任意命令。
- DeepSeek 密钥只注入子进程环境，不写日志，不返回前端。
- 输出统一执行 Token/API Key 脱敏。
- 复核员禁用工具，不参与实现。
- 服务重启时，中断任务标记为 `blocked`，不自动伪装成功。

## API

```text
GET  /api/health
GET  /api/agents
GET  /api/runs
GET  /api/runs/latest
POST /api/tasks
GET  /api/runs/{run_id}?after={event_id}
POST /api/tasks/{run_id}/{task_id}/accept
POST /api/tasks/{run_id}/{task_id}/retry
POST /api/runs/{run_id}/cancel
POST /api/runs/{run_id}/decision
GET  /api/artifacts/{run_id}
```

## 运行数据

```text
data/live-team.sqlite3
runtime/artifacts/{run_id}/
runtime/server.log
runtime/server-error.log
workspaces/{workspace}/
```

以上内容均由 `.gitignore` 排除，不进入代码仓库。

## 待决策门

当目标明确要求新闻条数，且小豆检索与小深分析都报告“数量不足、缺口、无法交付”时：

- 运行进入 `needs_decision`，立即停止昂贵调用。
- 不启动第二次联网检索或复核。
- 驾驶舱显示正式决策卡，老板可以选择：
  - 接受数量不足：复核只检查缺口、来源和风险是否诚实列明。
  - 扩大时间窗口：可选择近 3 / 7 / 30 天，清除旧上游结果后重新检索。
  - 取消任务。
- 决策写入 runs 表：`decision`、`decision_json`、`decision_at`。

## 当前限制

- Planner 仍是确定性规则，尚未交给 LLM 动态生成任意 DAG。
- 任务按依赖串行执行，尚未并行调度无依赖任务。
- 工程任务使用目标工作区现有代码，不自动复制外部仓库。
- 还没有向量记忆、团队 KPI、预算账单和跨项目队列。
- Claude 复核耗时通常长于其他成员，因此复核上下文已压缩并禁用工具。

## 下一阶段

1. 用 LLM Planner 替代确定性规则，并保留规则校验器。
2. 增加无依赖任务并行与文件所有权锁。
3. 增加工作树复制、测试命令白名单和独立测试环境。
4. 增加 Token、耗时、费用和返工率仪表盘。
5. 将验收通过的结论写入可检索的团队记忆。
