# AI 团队驾驶舱（磨坊办公室）

一个像素风的 Agent 协作办公室，把五个成员的工位摆在一块地板上，点谁看谁。

- 首屏：`打开驾驶舱.cmd` 双击，或直接打开 `index.html`
- 刷新数据：`node probe.mjs`（免费、1 秒）／`node probe.mjs --live`（真发一句话，有微量费用）

---

## 为什么没有直接装 munder-difflin

先说结论：**那个项目很好，但不适合这台机器现在装。**

| 对比项 | munder-difflin（原项目） | 本驾驶舱 |
|---|---|---|
| 技术栈 | Electron + React + Pixi.js + node-pty + xterm.js | 单文件 HTML + SVG，零依赖 |
| 安装 | `npm install`，还要编译 node-pty（需要 C/C++ 工具链） | 不用装，双击就开 |
| C 盘占用 | npm 缓存 + Electron + 重编译产物，量级几百 MB | **0**，全部文件在 E 盘 |
| 素材许可 | 像素素材是 LimeZu《Modern Interiors》，**禁止商用** | 像素小人是我按 10×14 网格自己画的 |
| 真实终端 | 每个 Agent 是真 PTY 进程，可打字进去 | 只做状态看板，不能接管终端 |
| 任务看板 / 邮箱 / 记忆 | 有 | 没有 |

你 C 盘只剩 18G（已用 89%），装它要付出几百 MB 加一个 C++ 工具链，收益只是"好看一点"。所以这里只**借鉴它的信息设计**——工位、状态灯、谁在干什么——重做一个轻的。

如果想要它的完整能力（真终端、任务看板、邮箱、记忆），可以以后再装，但建议先清 C 盘，或者指定 `npm_config_cache` 到 D/E 盘。

参考：
- 原项目 https://github.com/chaitanyagiri/munder-difflin （现指向 HarnessMD/munder-difflin）
- 设计要点：每个 agent 一张卡显示 status / engine / model / 上下文 / 当前 ticket / 当前动作；agent 走到工位、信封桌间飞；Michael 作为主管在独立办公室，只把花钱和破坏性操作上报给人

---

## 目录

```
cockpit/
├─ index.html         驾驶舱本体（约 20 KB，含全部样式与逻辑）
├─ probe.mjs          探活脚本，刷新 data/office.js
├─ data/
│  └─ office.js       数据快照（JS 而非 JSON，为了 file:// 能直接打开）
├─ preview.png        效果截图
└─ 打开驾驶舱.cmd      Windows 双击入口
```

总计约 170 KB。

## 界面上有什么

**左侧 · 办公室地板**
- 五个工位：小棒居中（主管位，蓝色描边），小深 / 小酷 / 小克 / 小豆 在下方一排
- 头顶状态灯：绿色呼吸 = 在线可派活，黄色 = 需人工确认，灰色 = 未连接
- 信封动画：每 5 秒从主管位飞向一个在线员工，示意派活
- 点工位 → 右侧详情切换；鼠标悬停 → 浮出名字和引擎

**右侧 · 三张卡**
1. 员工详情：头像、引擎、版本、最近活动、典型耗时、**能力边界**、能力标签、真实调用命令
2. 派活路由：什么活给谁
3. 今日成本：各场景典型代价 + 用量条（示意）

**底部 · 事件日志**
按时间倒序，最近 40 条。探活会往这里追加。

## 刷新数据

```bash
cd "E:/WorkBuddy工作空间/ai-team/cockpit"

node probe.mjs          # 只查版本/鉴权，不花钱，约 1 秒
node probe.mjs --live   # 真给每个员工发一句「只回复两个字：在线」，会产生少量 token
```

探活方式：

| 员工 | quick 模式 | live 模式 |
|---|---|---|
| 小深 | `bin.js --version` | headless 实呼，约 30s |
| 小酷 | `codex --version` | `codex exec`，约 12s |
| 小克 | `claude --version` | `claude -p`，秒级 |
| 小豆 | `GET /api/v3/models` 鉴权 | `chat/completions` 实呼，约 2s |

脚本会保留配色、座位、能力标签，只更新状态、耗时和日志。

## 改员工 / 加员工

直接编辑 `data/office.js`：

```js
{
  id: "xin",                    // 唯一 id
  name: "小新", role: "测试",
  engine: "某引擎", version: "1.0",
  status: "online",             // online | warn | offline
  seat: { x: 570, y: 360 },     // SVG 坐标：x 0-760，y 0-470
  colors: { hair:"#333", skin:"#f0c9a0", shirt:"#22c55e", pants:"#374151" },
  caps: ["能干什么"],
  last: "最近做了什么",
  latency: "典型耗时",
  limit: "不能干什么",           // 这一项最值钱，别省
  cmd: "调用命令"
}
```

座位坐标参考：地板高 470，墙占 0–100，主管位 `y:200`，员工排 `y:360`；一排四个的 x 分别是 `95 / 280 / 465 / 650`。

## C 盘占用

| 项 | 大小 |
|---|---|
| cockpit 全部文件 | ~170 KB（在 E 盘） |
| npm 安装 | 无 |
| 浏览器缓存 | 打开页面会产生常规缓存，量级极小 |

探活脚本用系统 Node（`D:\Program Files\nodejs`），不装任何包。
