/* 磨坊办公室 · 数据快照
   由 probe.mjs 自动生成（2026-11-14 20:47），也可手改。
   注意：这是 JS 而非 JSON —— 为了在 file:// 下也能直接双击打开（无 CORS 限制）。 */

window.OFFICE = {
  "generatedAt": "2026-11-14 20:47",
  "connectivity": "4/4 员工 + 老板",
  "agents": [
    {
      "id": "bang",
      "name": "小棒",
      "role": "老板 AI",
      "engine": "WorkBuddy",
      "version": "当前会话运行中",
      "status": "online",
      "seat": {
        "x": 380,
        "y": 200
      },
      "colors": {
        "hair": "#2f4b7c",
        "skin": "#f0c9a0",
        "shirt": "#38bdf8",
        "pants": "#1e293b"
      },
      "caps": [
        "拆活",
        "派活",
        "验收",
        "汇总",
        "联网查证",
        "生成图片"
      ],
      "last": "20:33 定稿三份团队模板",
      "latency": "即时 · 本会话",
      "limit": "不替你做决定；危险操作必须先问",
      "cmd": "当前会话即入口"
    },
    {
      "id": "shen",
      "name": "小深",
      "role": "推理拆解",
      "engine": "DSH · headless",
      "version": "0.2.2-rc.3",
      "status": "online",
      "seat": {
        "x": 95,
        "y": 360
      },
      "colors": {
        "hair": "#3a2a1e",
        "skin": "#eec39a",
        "shirt": "#8b5cf6",
        "pants": "#2b2f3a"
      },
      "caps": [
        "长链推理",
        "方案拆解",
        "读写本地文件",
        "起子进程"
      ],
      "last": "20:47 版本探活 / 462ms",
      "latency": "单次冷启动 30s 级",
      "limit": "不能多轮对话；不读凭据文件，须注入 DEEPSEEK_API_KEY",
      "cmd": "DSH_HOME=E:\\DSHDockData\\dsh-home\nELECTRON_RUN_AS_NODE=1 \"…/DSH NEXT.exe\" \"…/dsh/lib/bin.js\" --profile headless \"任务\""
    },
    {
      "id": "ku",
      "name": "小酷",
      "role": "工程实现",
      "engine": "Codex CLI",
      "version": "codex-cli 0.169.0-alpha.11.1",
      "status": "online",
      "seat": {
        "x": 280,
        "y": 360
      },
      "colors": {
        "hair": "#1f2937",
        "skin": "#f2d3b3",
        "shirt": "#22c55e",
        "pants": "#334155"
      },
      "caps": [
        "改代码",
        "跑命令",
        "批量文件",
        "reasoning high"
      ],
      "last": "20:47 版本探活 / 270ms",
      "latency": "12s / 300~8000 tok",
      "limit": "仅 danger-full-access 可用，必须 -C 锁目录",
      "cmd": "codex.exe exec --skip-git-repo-check \\\n  --sandbox danger-full-access -C \"目录\" \"任务\" < /dev/null"
    },
    {
      "id": "ke",
      "name": "小克",
      "role": "长文审阅",
      "engine": "Claude Code",
      "version": "2.1.318 (Claude Code)",
      "status": "online",
      "seat": {
        "x": 465,
        "y": 360
      },
      "colors": {
        "hair": "#4a3728",
        "skin": "#f0c9a0",
        "shirt": "#f59e0b",
        "pants": "#3f3f46"
      },
      "caps": [
        "长文审阅",
        "挑错",
        "对比差异",
        "严谨写作"
      ],
      "last": "20:47 版本探活 / 239ms",
      "latency": "秒级 · 按量",
      "limit": "非交互 -p，不能中途追问",
      "cmd": "cd \"目录\" && claude -p \"任务\" < /dev/null"
    },
    {
      "id": "dou",
      "name": "小豆",
      "role": "中文多模态",
      "engine": "豆包 · 方舟",
      "version": "doubao-seed-2-1-pro-260915",
      "status": "online",
      "seat": {
        "x": 650,
        "y": 360
      },
      "colors": {
        "hair": "#2b2b2b",
        "skin": "#f5d5b8",
        "shirt": "#ec4899",
        "pants": "#374151"
      },
      "caps": [
        "中文表达",
        "看图",
        "联网",
        "落盘",
        "16 个模型"
      ],
      "last": "20:47 鉴权通过 / 286ms",
      "latency": "问答 2s / 联网 25s",
      "limit": "无工具执行能力，碰不到文件系统",
      "cmd": "node doubao.mjs \"问题\" --image 图.png --web --out 路径.md"
    }
  ],
  "routing": [
    {
      "when": "要改代码、跑命令、批量处理",
      "to": "小酷"
    },
    {
      "when": "要想清楚、拆方案、写结构",
      "to": "小深"
    },
    {
      "when": "要挑错、审逻辑、对比两版",
      "to": "小克"
    },
    {
      "when": "要说人话、看图、查今天的事",
      "to": "小豆"
    },
    {
      "when": "拍板与对外",
      "to": "你"
    }
  ],
  "cost": {
    "chat": "2s / 80 tok",
    "web": "25s / 8000 tok",
    "code": "12s / 300~8000 tok",
    "free": "联网 20K 次",
    "usedPct": 18
  },
  "log": [
    {
      "t": "20:47",
      "who": "小深",
      "msg": "探活通过：版本探活 / 462ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:47",
      "who": "小酷",
      "msg": "探活通过：版本探活 / 270ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:47",
      "who": "小克",
      "msg": "探活通过：版本探活 / 239ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:47",
      "who": "小豆",
      "msg": "探活通过：鉴权通过 / 286ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:39",
      "who": "小深",
      "msg": "探活通过：版本探活 / 340ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:39",
      "who": "小酷",
      "msg": "探活通过：版本探活 / 152ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:39",
      "who": "小克",
      "msg": "探活通过：版本探活 / 141ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:39",
      "who": "小豆",
      "msg": "探活通过：鉴权通过 / 419ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:33",
      "who": "小棒",
      "msg": "定稿三份团队模板：开局词 / 员工清单 / 团队规矩",
      "ok": true
    },
    {
      "t": "20:12",
      "who": "小豆",
      "msg": "联网插件开通，实时汇率查证通过（25.7s / 7986 tok）",
      "ok": true
    },
    {
      "t": "20:09",
      "who": "小棒",
      "msg": "复扫已开通模型：16/27",
      "ok": true
    },
    {
      "t": "19:57",
      "who": "你",
      "msg": "方舟控制台完成模型开通",
      "ok": true
    },
    {
      "t": "19:46",
      "who": "小棒",
      "msg": "全团队实呼检测：小深 / 小酷 / 小克 均回「在线」",
      "ok": true
    },
    {
      "t": "19:42",
      "who": "小棒",
      "msg": "发现 codex 需 < /dev/null，否则卡死在等 stdin",
      "ok": true
    },
    {
      "t": "19:36",
      "who": "小棒",
      "msg": "第一把 Key 格式校验失败（22 字符，非 UUID 形态）",
      "bad": true
    },
    {
      "t": "19:13",
      "who": "小深",
      "msg": "豆包通道探测交付：结论「没通」，唯一缺口是 Key",
      "ok": true
    },
    {
      "t": "19:04",
      "who": "小酷",
      "msg": "Codex 通道打通，文件读写双向验证通过",
      "ok": true
    },
    {
      "t": "18:54",
      "who": "小深",
      "msg": "DSH headless 打通，加载 0.2.2-rc.3，落盘成功",
      "ok": true
    }
  ]
};
