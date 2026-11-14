你是小酷（Codex）。`index.html` 的「团队成果区」主体验收通过，只剩一个缺陷，改一处即可。

## 缺陷

`maybeAppendDemoArtifact()` 里写死了两个值：

```js
title: "工作台实现",
ownerId: "ku",
```

后果：跑完一次派活，成果区会出现一条标题叫「工作台实现」的**演示**条目，和真实成果里的「工作台实现」（就是 index.html 本身）完全撞名。老板扫一眼会以为是同一份东西，一份能复制路径一份不能。

## 改成

1. `title` 用派活单名：`title: jobName`（`jobName` 上面已经取好了，就是 `batch[0].jobName`）
2. `ownerId` 用实际干活的人：`ownerId: batch[0].ownerId`（取第一个子任务的负责人）

其余不动：`real: false`、`path: ""`、`◇ 演示` 标签、来源、时间、摘要、highlights 都保持现在这样，这些是对的。

## 自测

改完发布一次任务，确认成果区新增那条的名称是任务原文（例如「写一份客户名单，并审一遍逻辑」），不是「工作台实现」；且不再和真实那条撞名。

## 交付

覆盖 `index.html`，在 `build/REPORT-ku3.md` 末尾追加一节「补修：演示成果标题与负责人」，写清改前改后。

最后一行输出：`DONE4 bytes=<index.html 字节数>`
