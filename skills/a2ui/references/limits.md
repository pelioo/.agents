# 已知限制与降级策略

A2UI 不是万能解。Agent 在以下场景应**主动避开**或**降级**到 Markdown。

---

## 不适用场景

| 场景 | 原因 | 降级方案 |
|---|---|---|
| 单轮问答 / 纯文字解释 | 无 UI 价值，徒增协议开销 | Markdown 文本回复 |
| 输出需要被复制/粘贴/搜索 | A2UI 渲染后是 React 组件，无法选中复制 | Markdown（保留可复制性） |
| 极简单次性输出（"今天星期几"） | 协议开销大于收益 | 单行文本 |
| 内容长度超过 ~3000 字 | 大量 Text 组件性能差，且不利于阅读 | Markdown + 折叠 |
| 客户端不支持 `a2ui_render` | 协议无法解析 | 检测工具可用性，降级 Markdown |

---

## 性能与频率约束

- **更新频率**：单 surface 不超过 **5 秒/次**
- **真正高频数据流**（>1Hz，如实时行情/日志流）→ 用 `updateDataModel` 仍不够，应走 WebSocket 旁路，不进 A2UI
- **组件总数**：单 surface 建议 ≤200 个组件；超过考虑分页（多个 surfaceId）或聚合（MetricsGrid 替代多 MetricCard）
- **树深度**：建议 ≤3 层

---

## 容错行为

| 异常 | 前端行为 | Agent 应做 |
|---|---|---|
| 组件 ID 引用了不存在的子组件 | 跳过该子组件 | 检查 children 数组 ID 是否都已在 components 中定义 |
| `${path}` 引用了不存在的字段 | 渲染为空字符串 | 在下发前校验 dataModel 路径 |
| action 事件名未注册 | 静默丢弃 | 在 SKILL.md "Action 事件处理" 段维护事件名清单 |
| 同一 ID 不同次下发类型不一致 | 取最后一次定义 | 保持 ID 对应的 component 类型稳定 |

---

## 何时主动告知用户"已降级"

如果 Agent 检测到 `a2ui_render` 不可用或场景不适用，应在回复开头说明：

```markdown
（说明：当前环境不支持 A2UI 渲染，以下用 Markdown 等效表达）
```

避免默默降级让用户困惑。

---

## 速查决策表

| 需求 | 推荐方式 |
|---|---|
| 实时监控仪表盘 | A2UI ✅ |
| 一次性报告/总结 | Markdown |
| 用户可点击的操作面板 | A2UI ✅ |
| 需要复制粘贴的内容 | Markdown |
| 单轮问答 | Markdown |
| 长流程（>5 分钟） + 持续观察 | A2UI ✅ + updateDataModel |
| 客户端不支持 A2UI | Markdown |
| 实时行情/日志流（>1Hz） | WebSocket，不走 A2UI |