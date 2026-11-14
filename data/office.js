/* 磨坊办公室 · 数据快照
   由 probe.mjs 自动生成（2026-11-15 06:26），也可手改。
   注意：这是 JS 而非 JSON —— 为了在 file:// 下也能直接双击打开（无 CORS 限制）。 */

window.OFFICE = {
  "generatedAt": "2026-11-15 06:26",
  "connectivity": "4/4 员工 + 老板",
  "agents": [
    {
      "id": "bang",
      "name": "小棒",
      "role": "老板 AI",
      "engine": "WorkBuddy",
      "logo": "wb",
      "version": "当前会话运行中",
      "status": "online",
      "ms": null,
      "tokens": null,
      "caps": [
        "拆活派活",
        "验收",
        "汇总",
        "联网查证",
        "生成图片"
      ],
      "last": "20:56 改版工作台界面",
      "latency": "即时 · 本会话",
      "limit": "不替你做决定；删除、覆盖、改环境变量、花钱必须先问",
      "cmd": "当前会话即入口，无需命令"
    },
    {
      "id": "shen",
      "name": "小深",
      "role": "推理拆解",
      "engine": "DeepSeek Harness",
      "logo": "deepseek",
      "version": "0.2.2-rc.3",
      "status": "online",
      "ms": 5748,
      "tokens": null,
      "caps": [
        "长链推理",
        "方案拆解",
        "读写本地文件",
        "起子进程"
      ],
      "last": "06:26 实呼成功 / 5.7s",
      "latency": "单次冷启动 30s 级",
      "limit": "不能多轮对话；不读凭据文件，须注入 DEEPSEEK_API_KEY",
      "cmd": "export DSH_HOME='E:\\DSHDockData\\dsh-home'\nexport DEEPSEEK_API_KEY=$(grep -oE 'sk-[A-Za-z0-9_-]{20,}' \"$DSH_HOME/.credentials.yaml\" | head -1)\nELECTRON_RUN_AS_NODE=1 \"D:\\Program Files\\DSH NEXT\\DSH NEXT.exe\" \"D:\\Program Files\\DSH NEXT\\resources\\app.asar\\node_modules\\@deepseek-ai\\dsh\\lib\\bin.js\" --profile headless \"任务\""
    },
    {
      "id": "ku",
      "name": "小酷",
      "role": "工程实现",
      "engine": "Codex CLI",
      "logo": "openai",
      "version": "0.169.0-alpha.11.1",
      "status": "online",
      "ms": 44402,
      "tokens": null,
      "caps": [
        "改代码",
        "跑命令",
        "批量文件",
        "reasoning high"
      ],
      "last": "06:26 实呼成功 / 44.4s",
      "latency": "12s / 300~8000 tok",
      "limit": "仅 danger-full-access 可用，必须用 -C 锁目录并事后核对改动",
      "cmd": "\"D:\\WindowsApps\\OpenAI.Codex_26.1111.2228.0_x64__2p2nqsd0c76g0\\app\\resources\\codex.exe\" exec --skip-git-repo-check --sandbox danger-full-access -C \"E:\\WorkBuddy工作空间\\ai-team\\cockpit\" \"任务\" < /dev/null"
    },
    {
      "id": "ke",
      "name": "小克",
      "role": "长文审阅",
      "engine": "Claude Code",
      "logo": "claude",
      "version": "2.1.318",
      "status": "online",
      "ms": 5050,
      "tokens": null,
      "caps": [
        "长文审阅",
        "挑错",
        "对比差异",
        "严谨写作"
      ],
      "last": "06:26 实呼成功 / 5.0s",
      "latency": "秒级 · 按量",
      "limit": "非交互模式，不能中途追问；不主动跨盘操作",
      "cmd": "cd \"E:\\WorkBuddy工作空间\\ai-team\\cockpit\" && \"D:\\Programs\\claude-code\\claude.exe\" -p \"任务\" < /dev/null"
    },
    {
      "id": "dou",
      "name": "小豆",
      "role": "中文多模态",
      "engine": "豆包 · 火山方舟",
      "logo": "doubao",
      "version": "doubao-seed-2-1-pro-260915",
      "status": "online",
      "ms": 1714,
      "tokens": 52,
      "caps": [
        "中文表达",
        "看图",
        "联网",
        "落盘",
        "16 个模型"
      ],
      "last": "06:26 实呼成功 / 52 tok / 1.7s",
      "latency": "问答 2s / 联网 25s",
      "limit": "无工具执行能力，碰不到文件系统；联网一次约 8000 tokens",
      "cmd": "node \"E:\\WorkBuddy工作空间\\doubao-bridge\\doubao.mjs\" \"任务\" --web"
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
      "when": "拍板、对外发送",
      "to": "你"
    }
  ],
  "cost": {
    "mode": "按量计费",
    "note": "探活免费，实呼才走额度",
    "chat": "2s / 80 tok",
    "web": "25s / 8000 tok",
    "code": "12s / 300~8000 tok",
    "free": "联网 20K 次/月"
  },
  "log": [
    {
      "t": "06:26",
      "who": "小深",
      "msg": "探活通过：实呼成功 / 5.7s",
      "ok": true,
      "bad": false
    },
    {
      "t": "06:26",
      "who": "小酷",
      "msg": "探活通过：实呼成功 / 44.4s",
      "ok": true,
      "bad": false
    },
    {
      "t": "06:26",
      "who": "小克",
      "msg": "探活通过：实呼成功 / 5.0s",
      "ok": true,
      "bad": false
    },
    {
      "t": "06:26",
      "who": "小豆",
      "msg": "探活通过：实呼成功 / 52 tok / 1.7s",
      "ok": true,
      "bad": false
    },
    {
      "t": "06:26",
      "who": "小深",
      "msg": "探活通过：版本探活 / 1.0s",
      "ok": true,
      "bad": false
    },
    {
      "t": "06:26",
      "who": "小酷",
      "msg": "探活通过：版本探活 / 902ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "06:26",
      "who": "小克",
      "msg": "探活通过：版本探活 / 894ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "06:26",
      "who": "小豆",
      "msg": "探活通过：鉴权通过 / 309ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "21:00",
      "who": "小深",
      "msg": "探活通过：版本探活 / 464ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "21:00",
      "who": "小酷",
      "msg": "探活通过：版本探活 / 264ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "21:00",
      "who": "小克",
      "msg": "探活通过：版本探活 / 246ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "21:00",
      "who": "小豆",
      "msg": "探活通过：鉴权通过 / 366ms",
      "ok": true,
      "bad": false
    },
    {
      "t": "20:56",
      "who": "小棒",
      "msg": "界面改版：像素风 → 办公平台风格，头像换为各产品官方标志",
      "ok": true
    },
    {
      "t": "20:50",
      "who": "小棒",
      "msg": "工作台推送至 GitHub · keystandy/ai-team-cockpit",
      "ok": true
    },
    {
      "t": "20:47",
      "who": "小棒",
      "msg": "探活通过 5/5，路径抽离为 local.config.json",
      "ok": true
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
      "t": "19:57",
      "who": "你",
      "msg": "方舟控制台完成模型开通，可用模型 16 个",
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
      "t": "19:04",
      "who": "小酷",
      "msg": "Codex 通道打通，文件读写双向验证通过",
      "ok": true
    }
  ]
};
