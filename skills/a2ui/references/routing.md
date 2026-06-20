# 完整决策路由

> 这是 SKILL.md 中 "Quick routing 表格" 的详细决策树版。
> 简表看 SKILL.md，需要权衡 token 成本、决策分支时再读本文。

不知道该读哪些 references？看下面的决策树。

---

## 决策流程

```
你想做什么？
│
├─ 简单 UI（1-3 个组件，无交互）
│   └─ SKILL.md 即可
│
├─ 中等面板（仪表盘、监控 5-10 个组件）
│   ├─ 静态（一次渲染完）
│   │   ├─ 包含 MetricCard/MetricsGrid？  → 读 components.md
│   │   └─ 只用基础组件（Card + Text + Button）  →  SKILL.md 即可
│   │
│   └─ 需要定期刷新（监控）
│       └─ 读 data-binding.md（学会用 updateDataModel）
│
├─ 高频更新（每 5-30 秒刷新数据）
│   └─ 读 scripts.md（用 a2ui_diff.py 自动算最小 diff）
│
├─ 交互面板（按钮点击触发 Agent 动作）
│   └─ 读 events.md（学会 action 事件格式 + [User Action] 处理）
│
├─ 复杂组合（多卡片 + 表单 + 向导 + 数据绑定）
│   ├─ 读 components.md（完整组件属性表）
│   ├─ 读 data-binding.md（数据绑定）
│   ├─ 读 events.md（按钮交互）
│   └─ 读 best-practices.md（设计原则）
│
└─ 出错了 / 不确定该不该用 A2UI
    ├─ UI 不显示 → implementations.md（确认客户端支持）
    ├─ UI 异常 / 性能差 → limits.md（容错 + 频率限制）
    └─ 不知道 A2UI 是否合适 → limits.md（不适用场景段）
```

---

## Token 成本估算（按加载量）

| 加载量 | tokens（约） | 适用场景 |
|---|---|---|
| 仅 SKILL.md | ~1200 | 简单面板 / 一次性输出 |
| + 1 个 reference | ~2500 | 大多数场景 |
| + 2 个 references | ~3500 | 中等复杂 |
| + 3+ 个 references | ~4500 | 全功能使用 |

**目标**：大多数场景保持在 1-2 个 references（~2500 tokens 以内）。

---

## 如果仍然不知道

1. 看 [SKILL.md 的 Quick routing 段](../SKILL.md#quick-routing) 的对照表
2. 看 [limits.md](limits.md) 的"不适用场景"段，确认 A2UI 是不是真的适合
3. 如果是第一次用，建议读完整本文件 + best-practices.md，建立完整心智模型

---

## 为什么不做成单一长文件

仓库规范（AGENTS.md 第 234 行）鼓励把长内容移到 references/，原因：

1. **节省 token**：Agent 不需要的内容不进 context
2. **更易维护**：单文件改动影响范围小
3. **更清晰的关注点分离**：核心规则 vs 详细参考 vs 边缘场景

SKILL.md 现在只包含**最低必要信息**（~100 行）+ 路由指引。其他内容按需加载。