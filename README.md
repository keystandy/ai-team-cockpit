# AI 协作工作台

一个用来看住五个 AI 员工的工作台：谁在线、刚做了什么、能派什么活、边界在哪。点左侧成员切换详情。

- 打开：双击 `打开驾驶舱.cmd`，或直接开 `index.html`
- 刷新：`node probe.mjs`（免费，约 1 秒）／`node probe.mjs --live`（真发一句话，有微量费用）

![界面预览](preview.png)

---

## 界面

**左侧 · 团队成员**
五个成员，各自的产品标志 + 名称 + 角色 + 状态点（绿=在线、黄=需确认、灰=离线）。点一下切换右侧详情。

**顶部 · 四个指标**
在线成员数、平均探活耗时、活动记录条数、当前计费方式。全部由 `data/office.js` 实时算出。

**中间左 · 成员工作台**
选中成员的完整档案：产品标志、引擎、版本、在线状态、最近活动、探活耗时、典型耗时、能力标签、**能力边界**（黄色警示条）、真实调用命令（可一键复制）、该成员最近的 3 条记录。

**中间右 · 派活路由 + 成本参考**
什么活该给谁，五条规则。下面是各场景的典型代价，派活前扫一眼。

**底部 · 活动流**
按时间倒序的事件表，支持右上角搜索框过滤。

## 成员与标志

| 代号 | 引擎 | 标志 |
|---|---|---|
| 小棒 | WorkBuddy | 自绘的 W 标记（该产品无公开标志） |
| 小深 | DeepSeek Harness | DeepSeek 官方彩色标志 |
| 小酷 | Codex CLI | OpenAI 官方标志 |
| 小克 | Claude Code | Claude 官方彩色标志 |
| 小豆 | 豆包 · 火山方舟 | 豆包官方彩色标志 |

图标取自 [@lobehub/icons-static-svg](https://github.com/lobehub/lobe-icons)（MIT），内联进 `assets/logos.js`，页面不请求任何外部资源。各标志的商标权归各自权利人所有，此处仅用于标识对应产品。

## 为什么没有直接装 munder-difflin

这个工作台参考了 [munder-difflin](https://github.com/chaitanyagiri/munder-difflin) 的信息设计（每个 agent 一张卡：状态、引擎、模型、当前任务、当前动作；主管只把花钱和破坏性操作上报给人），但没有装它：

| 对比 | munder-difflin | 本工作台 |
|---|---|---|
| 技术栈 | Electron + React + Pixi.js + node-pty + xterm.js | 单页 HTML + CSS + 原生 JS，零依赖 |
| 安装 | `npm install`，还要编译 node-pty（需要 C/C++ 工具链） | 不用装，双击就开 |
| C 盘占用 | npm 缓存 + Electron + 重编译产物，几百 MB 量级 | **0**，全部文件在本地项目目录 |
| 真实终端 | 每个 Agent 是真 PTY 进程，可以打字进去 | 只做状态看板，不接管终端 |
| 任务看板 / 邮箱 / 记忆 | 有 | 没有 |

它需要付出几百 MB 和一个 C++ 工具链，换来的是"能真的接管终端"。只要看状态的话，静态页足够。

## 目录

```
.
├─ index.html                    工作台本体（单文件，含全部样式与逻辑）
├─ probe.mjs                     探活脚本，刷新 data/office.js
├─ data/
│  └─ office.js                  数据快照（JS 而非 JSON，为了 file:// 能直接打开）
├─ assets/
│  └─ logos.js                   五个产品标志（内联 SVG）
├─ local.config.example.json     本机路径配置模板
├─ preview.png                   效果截图
└─ 打开驾驶舱.cmd                 Windows 双击入口
```

## 刷新数据

```bash
node probe.mjs          # 只查版本/鉴权，不花钱，约 1 秒
node probe.mjs --live   # 真给每个员工发一句「只回复两个字：在线」，会产生少量 token
```

| 员工 | quick 模式 | live 模式 |
|---|---|---|
| 小深 | `bin.js --version` | headless 实呼，约 30s |
| 小酷 | `codex --version` | `codex exec`，约 12s |
| 小克 | `claude --version` | `claude -p`，秒级 |
| 小豆 | `GET /api/v3/models` 鉴权 | `chat/completions` 实呼，约 2s |

脚本会保留标志、能力标签、命令，只更新状态、耗时、版本和日志。

### 换台机器怎么用

四个员工的程序路径因机器而异。复制 `local.config.example.json` 为 `local.config.json`，改里面的路径即可；这个文件已被 `.gitignore` 忽略，不会上传。不建也能跑，会退回源码里的默认值。

```bash
cp local.config.example.json local.config.json
# 然后改 dshExe / codexExe / claudeExe / arkCredentials 这几项
```

哪一项路径不对，那个员工就显示离线——不会崩，只是探活失败，活动流里能看到原因。

## 改成员 / 加成员

编辑 `data/office.js`：

```js
{
  id: "xin",                    // 唯一 id
  name: "小新", role: "测试",
  engine: "某引擎",
  logo: "wb",                   // wb | openai | deepseek | claude | doubao
  version: "1.0",
  status: "online",             // online | warn | offline
  ms: null,                     // 探活耗时，脚本会覆盖
  caps: ["能干什么"],
  last: "最近做了什么",
  latency: "典型耗时",
  limit: "不能干什么",           // 这一项最值钱，别省
  cmd: "调用命令"
}
```

想加新标志，在 `assets/logos.js` 里加一个 `key: '<svg…>'`，再在 `index.html` 的 `TINT` / `INK` 里补一行配色。

## C 盘占用

| 项 | 大小 |
|---|---|
| 全部文件 | 约 250 KB |
| npm 安装 | 无 |
| 外部资源请求 | 无（标志是内联 SVG） |

探活脚本用系统 Node，不装任何包。
