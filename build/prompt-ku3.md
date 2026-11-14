你是小酷（Codex），本工作台实现负责人。现在给主区加一块「团队成果区」，位置在四张员工卡正下方。

## 输入（都在 `E:\WorkBuddy工作空间\ai-team\cockpit`）

- `build/SPEC-ARTIFACTS.md` —— 这一块的**唯一设计依据**，照它做，不许自己发挥
- `build/SPEC.md` —— 主规格，颜色字号圆角间距只能从这里取
- `build/strings.md` —— 术语，照它写文案
- `data/artifacts.js` —— **我已经准备好的真实成果种子数据**（`window.ARTIFACTS`），不要改它
- `index.html` —— 当前线上版本，在它基础上改，**直接改这个文件**

## 任务

在 `index.html` 里：

1. 在 `<script src="data/office.js"></script>` 后面加一行 `<script src="data/artifacts.js"></script>`（**路径就是 `data/artifacts.js`，不要写 `../`**，这个文件在项目根下）
2. 在员工卡组下方新增「团队成果」卡片，严格照 `SPEC-ARTIFACTS.md` 第 2、3 节：标题栏（T2 标题 + T4 计数 + 右侧 全部｜真实｜演示 筛选）、一行一条成果、两行式（名称行 + 元信息行）
3. 渲染 `window.ARTIFACTS` 里的 5 条真实成果。**这些数据一个字都不要改**，只负责显示
4. 派活单全部子任务完成后，自动追加一条演示成果（`real:false`），标签 `◇ 演示`，来源填该派活单名 + 子任务名

## 三个技术要点，务必做对

**A. 绝对路径必须由页面自己推算，不许写死盘符**

页面运行在 `file://` 下，项目根可以从 `location` 拿到：

```js
// file:///E:/WorkBuddy工作空间/ai-team/cockpit/index.html
// → 根目录 E:\WorkBuddy工作空间\ai-team\cockpit
const p = decodeURIComponent(location.pathname);      // /E:/WorkBuddy工作空间/ai-team/cockpit/index.html
const root = p.replace(/\/[^/]*$/, '').replace(/^\//, ''); // E:/WorkBuddy工作空间/ai-team/cockpit
const abs = root.replace(/\//g, '\\') + '\\' + relativePath.replace(/\//g, '\\');
```

复制路径按钮复制的是 `abs`。用 `navigator.clipboard`，失败时降级到临时 textarea + `document.execCommand('copy')`。

**B. 「查看」打不开真实文件，只能看摘要**

`file://` 下 `fetch` 本地文件会被浏览器拦。所以「查看」打开的是浮层，内容来自 `data/artifacts.js` 里的 `summary` 和 `highlights` 字段，外加真实路径。**不许假装读到了文件内容**，也不许留一个点了没反应的按钮。

**C. 主区内容变高了，不能把成果区裁掉**

现在主区是固定高度、内部不滚动的话，成果区会顶出可视区。改成：主区整体纵向可滚动（或员工卡组与成果区所在容器可滚动），保证 1440×900 下滚动一屏就能看到成果区标题和前几条；右栏保持独立不动。

## 硬约束

- 颜色、字号、圆角、间距**只能取 `build/SPEC.md` 已定义的变量**。`SPEC-ARTIFACTS.md` 第 9 节已明确「无新增变量」，你要是觉得非加不可，先停下在报告里写理由，不要自己加
- 字号只用 T1–T5；圆角只用 4 / 8 / 999；间距只用 4 的倍数
- 禁止阴影堆叠、发光、渐变、无限循环动画
- 零外部请求
- 不许动：老板输入框、小棒卡、四张员工卡、右栏三段、五个 logo
- 不许改 `data/office.js`、`data/artifacts.js`、`assets/logos.js`
- 术语照 `build/strings.md`

## 自测（做完自己跑，写进报告）

1. 1440×900 下，滚动能看到「团队成果」标题 + 至少 2 条成果，且员工卡没被裁
2. 1280×800 下同样成立，无横向滚动条
3. 点「复制路径」，剪贴板里是完整 Windows 绝对路径（形如 `E:\WorkBuddy工作空间\ai-team\cockpit\build\SPEC.md`），不是相对路径
4. 点「查看」，浮层出现且显示摘要 + 路径 + 演示/真实标签
5. 筛选切「演示」，列表只剩演示条目；切「真实」，只剩 5 条真实成果
6. 发布一次任务，跑完后成果区多出一条带 `◇ 演示` 的条目，计数从「真实 5 · 演示 0」变成「真实 5 · 演示 1」
7. 断网打开无报错、无外部请求

## 交付

改完写 `build/REPORT-ku3.md`：逐条写七项自测的实际结果（通过 / 不通过 + 证据），以及你实现路径推算的具体写法。

最后一行输出：`DONE3 bytes=<index.html 新字节数>`
