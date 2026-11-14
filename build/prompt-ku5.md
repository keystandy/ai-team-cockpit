你是小酷（Codex）。现在修一个派活设计缺陷：小深（推理拆解）三类子任务都轮不到他，永远是闲的。给他加一类**专属子任务**。

## 背景

`index.html` 里 `KIND_META` 现在三类：执行（小酷）、复核（小克）、检索（小豆）。`pickOwner()` 逻辑是「首选负责人不在线才用 fallback」，而三类的 fallback 都是小深——三个人都在线时，小深永远接不到活。

## 任务：新增第四类「拆解任务」，负责人固定小深

### 1. `KIND_META` 加一项

```js
planning: {
  title: "拆解任务",
  word: "拆解",
  ownerId: "shen",
  fallbackOwnerId: "ku",
  duration: 1800        // 与执行任务同量级
}
```

注意 `fallbackOwnerId` 是 `ku` 不是 `shen`——他自己就是首选，别再兜回自己。

### 2. `detectKinds()` 加识别规则

命中这些词就加一路 planning：`方案` `拆解` `规划` `结构` `设计` `思路` `分析`

要求：

- planning **排在最前**（先拆解、再执行、后复核/检索），因为它逻辑上发生在最前
- 现有规则全部保留：`写|改|实现` → execution，`审|检查|校对` → review，`查|最新|联网` → search
- 「至少两路（执行 + 复核）」的兜底逻辑**不变**，只在原有基础上按需插入 planning
- 上限仍是 4 路（`slice(0,4)`）
- **不许为了让小深接活而硬塞**：没命中触发词就不出现 planning，不能变成"每次都有拆解"

### 3. 派活单要能显示小深的命令

`data/office.js` 里小深的 `cmd` 我刚修好了（之前是省略号残路径），现在是完整的：

```
export DSH_HOME='E:/DSHDockData/dsh-home'
export DEEPSEEK_API_KEY=$(grep -oE 'sk-[A-Za-z0-9_-]{20,}' "$DSH_HOME/.credentials.yaml" | head -1)
ELECTRON_RUN_AS_NODE=1 "D:/Program Files/DSH NEXT/DSH NEXT.exe" "D:/Program Files/DSH NEXT/resources/app.asar/node_modules/@deepseek-ai/dsh/lib/bin.js" --profile headless "任务"
```

确认派活单渲染时会用 `agent.cmd` 把这个多行命令完整显示出来（多行要保留换行，不要压成一行，不要截断）。

### 4. 小深的卡片要能正常显示任务

现在他永远「暂无任务」。加了 planning 后应该能显示「拆解任务」。检查员工卡的任务显示逻辑对 shen 是否生效。

## 不许动

- 设计规格（`build/SPEC.md`、`build/SPEC-ARTIFACTS.md`）里的颜色、字号、圆角、间距
- 老板输入框、小棒卡、右栏三段、五个 logo
- `data/artifacts.js`、`assets/logos.js`
- 成果区逻辑
- 术语照 `build/strings.md`（用「拆解任务」，不用「规划任务」「分析任务」）

## 自测（做完自己跑，写进报告）

1. 输入「把这批素材做一版改造方案」→ 派活单里出现「拆解任务 · 小深」，同时仍有「执行任务 · 小酷」和「复核任务 · 小克」
2. 输入「核对一下名单」→ **不出现**拆解任务（没命中触发词）
3. 小深的卡片上显示「拆解任务」，不再永远是「暂无任务」
4. 派活单里小深的命令是多行完整路径，没有省略号、没有被截断
5. 输入含「查最新」→ 四路齐全：拆解 + 执行 + 复核 + 检索，不超过 4 条
6. 1440×900 与 1280×800 下派活单排版不错乱

## 交付

覆盖 `index.html`，写 `build/REPORT-ku5.md` 记录六项自测结果（通过 / 不通过 + 证据）。

最后一行输出：`DONE5 bytes=<index.html 字节数>`
