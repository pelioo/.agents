# 最佳实践

设计 A2UI 面板时的推荐做法。读完这一篇能让你的 UI 体验上一个台阶。

---

## 调用模式

### 首次渲染

**始终**把 `createSurface` 和 `updateComponents` 放在同一次 `a2ui_render` 调用的 messages 数组中：

```json
{"messages": [
  {"createSurface": {"surfaceId": "main", "catalogId": "cteno/v1"}},
  {"updateComponents": {"surfaceId": "main", "components": [...]}},
  {"updateDataModel": {"surfaceId": "main", "data": {...}}}
]}
```

原因：避免组件先以空数据渲染再被 dataModel 替换的闪烁。

### 增量更新

后续只发送 `updateComponents` 或 `updateDataModel`，**包含变化的组件/字段即可**：

- **结构变化**（增/删组件、改 children）→ `updateComponents`
- **纯数据变化**（指标数字、状态值、进度）→ `updateDataModel`（更省 token）

### 更新频率

**不要超过每 5 秒一次**（确保流畅的用户体验）。

真正高频（>1Hz）的数据流应该走 WebSocket 旁路，不进 A2UI。

---

## 组件 ID 命名

使用**语义化 ID**，清晰表达组件含义：

| 推荐 | 避免 |
|---|---|
| `"followers-metric"` | `"comp-1"` |
| `"progress-bar"` | `"p1"` |
| `"start-btn"` | `"b"` |
| `"status-indicator"` | `"indicator"` |
| `"feed-activity"` | `"feed"` |

**好处**：
- Diff 时容易识别"哪个组件变了"
- 调试时看日志就知道组件作用
- 同名组件（如两个 Progress）也能区分

---

## 组件树结构

- 保持树形结构**相对扁平**，建议 **2-3 层深度**
- 使用 `Card` 分组关联内容
- 优先使用 `MetricsGrid` 而非手动创建多个 `MetricCard`
- 使用 `Row` 水平排列同级组件，`Column` 垂直排列

**典型 3 层结构**：

```
Container (root)
├── StatusIndicator
└── Card
    ├── Progress
    ├── MetricsGrid (内部自动布局)
    └── ActivityFeed
```

---

## 复合组件 vs 手动组合

### 优先用复合组件

| 场景 | 推荐 | 避免 |
|---|---|---|
| 2+ 个指标 | `MetricsGrid` | 手动 Row + 多个 MetricCard |
| 带时间戳的活动 | `ActivityFeed` | 手动 Column + 多个 ListItem |
| 多个并列按钮 | `ButtonGroup` | 手动 Row + 多个 Button |

复合组件自动处理布局、空格、视觉一致性，手动组合容易出错。

### 什么时候手动组合

- 需要自定义子组件布局（如 MetricsGrid 内混用 MetricCard 和自定义组件）
- 需要每个子组件独立的 action/状态（如可点击的指标卡）
- 复合组件不支持的特殊场景

---

## 何时用 dataModel vs 组件属性

**能用 `${path}` 引用 dataModel 字段就用它**：

```json
// 推荐：dataModel 绑定
{"id": "followers", "component": "MetricCard",
 "value": "${stats.followers}", "label": "粉丝数"}

// 不推荐：硬编码值（每次更新都要重发组件）
{"id": "followers", "component": "MetricCard",
 "value": "5172", "label": "粉丝数"}
```

**例外**：完全静态的、永远不变的值（如 Card 的标题）可以直接写死。

---

## 常见反模式

| 反模式 | 问题 | 正确做法 |
|---|---|---|
| 每次 update 都重发整棵组件树 | 浪费 token，触发整页重渲染 | 只 update 变化的部分 |
| 嵌套超过 3 层 | 维护难，性能差 | 拆多个 Card |
| 用 `b1/b2/b3` 作 ID | diff 时无法识别 | 用语义化 ID |
| 把所有数据塞进一个 MetricCard | 信息密度过高 | 用 MetricsGrid 分拆 |
| 在 Card title 里硬编码动态值 | 改 title 要重发整个 Card | 用 `${path}` 引用 dataModel |
| 用 ListItem 表示可勾选的项 | ListItem 不支持 checked | 用 ChecklistItem |

---

## 性能优化 checklist

发布前检查：

- [ ] 结构（createSurface + updateComponents）只发一次
- [ ] 数据更新走 `updateDataModel`，不走 `updateComponents`
- [ ] 组件 ID 语义化
- [ ] 组件树 ≤3 层深度
- [ ] 单 surface 组件数 ≤200
- [ ] 更新频率 ≤5 秒/次
- [ ] 高频数据流不通过 A2UI（用 WebSocket）
- [ ] 优先用 MetricsGrid / ActivityFeed / ButtonGroup 复合组件
- [ ] dataModel 路径都用 `${path}` 引用，避免硬编码