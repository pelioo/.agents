# A2UI 组件参考（cteno/v1 目录）

完整的 19 个组件属性表。当 SKILL.md 主体的描述不够用时，按需查阅本文件。

## 目录

- [布局组件](#布局组件) — Container / Row / Column / Card / Divider
- [文本组件](#文本组件) — Text（5 种 variant）
- [数据展示](#数据展示) — Progress / MetricCard / StatusIndicator / Badge
- [列表组件](#列表组件) — List / ListItem / ChecklistItem
- [交互组件](#交互组件) — Button / ButtonGroup
- [媒体组件](#媒体组件) — Image / Icon
- [复合组件](#复合组件) — MetricsGrid / ActivityFeed
- [组件属性速查](#组件属性速查)

---

## 布局组件

### Container — 根布局容器

页面的根容器，所有组件树的起点。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `padding` | number | 否 | 内边距（像素） |
| `maxWidth` | number | 否 | 最大宽度 |
| `background` | string | 否 | 背景色（CSS 颜色值） |
| `children` | string[] | 否 | 子组件 ID 列表 |

### Row — 水平布局

水平排列子组件（flex-direction: row）。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `gap` | number | 否 | 子组件间距 |
| `align` | string | 否 | 垂直对齐方式（flex alignItems） |
| `justify` | string | 否 | 水平分布方式（flex justifyContent） |
| `children` | string[] | 否 | 子组件 ID 列表 |

### Column — 垂直布局

垂直排列子组件（flex-direction: column）。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `gap` | number | 否 | 子组件间距 |
| `align` | string | 否 | 水平对齐方式 |
| `children` | string[] | 否 | 子组件 ID 列表 |

### Card — 卡片容器

带边框和圆角的容器，用于分组关联内容。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 否 | 卡片标题 |
| `children` | string[] | 否 | 子组件 ID 列表 |

### Divider — 分割线

细线分隔符，无属性。

---

## 数据展示组件

### Text — 文本

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 文本内容 |
| `variant` | string | 否 | 样式变体：`"heading"` / `"subheading"` / `"body"` / `"caption"` / `"code"` |
| `markdown` | bool | 否 | 是否启用 Markdown 渲染 |

### Progress — 进度条

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `value` | number | 是 | 进度值，范围 0.0 ~ 1.0 |
| `label` | string | 否 | 进度说明文本 |

### MetricCard — 指标卡片

单个关键指标的展示卡片。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `value` | string/number | 是 | 指标值 |
| `label` | string | 是 | 指标名称 |
| `trend` | string | 否 | 趋势变化（如 `"+58"`, `"-0.1%"`） |
| `trendDirection` | string | 否 | 趋势方向：`"up"` / `"down"` |

### StatusIndicator — 状态指示器

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 是 | 状态：`"active"` / `"idle"` / `"error"` |
| `text` | string | 是 | 状态说明文本 |

### Badge — 徽标

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 徽标文本 |
| `variant` | string | 否 | 样式变体：`"info"` / `"success"` / `"warning"` / `"error"` |

---

## 列表组件

### List — 列表容器

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 否 | 列表标题 |
| `children` | string[] | 否 | 子组件 ID 列表（ListItem 或 ChecklistItem） |

### ListItem — 列表项

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 主文本 |
| `icon` | string | 否 | 图标名称（Ionicons） |
| `secondaryText` | string | 否 | 副文本 |
| `action` | object | 否 | 点击动作（同 Button 的 action 格式） |

### ChecklistItem — 清单项

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 清单文本 |
| `checked` | bool | 是 | 是否已完成 |

---

## 交互组件

### Button — 按钮

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | string | 是 | 按钮文本 |
| `variant` | string | 否 | 样式变体：`"primary"` / `"secondary"` / `"danger"` |
| `icon` | string | 否 | 图标名称（Ionicons） |
| `action` | object | 否 | 点击动作：`{"event": {"name": "事件名", "data": {...}}}` |

### ButtonGroup — 按钮组

水平排列多个按钮。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `children` | string[] | 否 | 子组件 ID 列表（Button） |

---

## 媒体组件

### Image — 图片

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `src` | string | 是 | 图片 URL |
| `alt` | string | 否 | 替代文本 |
| `caption` | string | 否 | 图片说明 |

### Icon — 图标

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | Ionicons 图标名称 |
| `color` | string | 否 | 图标颜色 |
| `size` | number | 否 | 图标大小 |

---

## 复合组件

复合组件是常见模式的语法糖，内部自动生成子组件。

### MetricsGrid — 指标网格

自动布局的指标卡片网格，比手动创建多个 MetricCard 更简洁。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `metrics` | Record<string, string/number> | 是 | 键值对形式的指标数据 |

### ActivityFeed — 活动流

带时间戳的垂直活动记录。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `items` | array | 是 | 活动条目：`[{"text": "描述", "timestamp": "10:30"}]` |

---

## 选型速查表

当你需要"展示 X"但不确定用哪个组件时，按下表对照：

| 你想做的 | 推荐组件 |
|---|---|
| 一段文字/标题 | `Text`（按层级选 `variant`） |
| 数值 + 趋势变化 | `MetricCard` |
| 多个数值快速展示 | `MetricsGrid` |
| 进度可视化 | `Progress` |
| 运行/暂停/异常状态 | `StatusIndicator` |
| 标签/分类 | `Badge` |
| 一组选项/步骤/活动 | `List` + `ListItem` |
| 待办/已办清单 | `List` + `ChecklistItem` |
| 用户点击触发动作 | `Button` 或 `ButtonGroup` |
| 一组按钮并列 | `ButtonGroup` |
| 分割线 | `Divider` |
| 分组卡片 | `Card`（带 title） |
| 时间戳列表 | `ActivityFeed` |
| 图片 | `Image` |
| 单个图标 | `Icon` |