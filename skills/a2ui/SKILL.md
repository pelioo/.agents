---
name: a2ui
description: "Guide for composing A2UI declarative UI components to build user-facing dashboards, monitoring panels, and interactive interfaces. Use when the user asks to render data as UI, build a dashboard, show progress visually, add clickable buttons, or replace long markdown output with structured cards."
license: MIT
---

# A2UI Interface Builder

A2UI 是声明式 UI 协议(基于 Google A2A 规范 v0.9)。Agent 通过 `a2ui_render` 工具发送 JSON 消息,前端按 catalog(默认 `cteno/v1`)解析组件 schema 渲染为原生组件。技术栈不限(React Native / Web / Flutter 等均可,只要支持 catalog)。

## Quick routing

**读完本段后按需加载 references,避免一次性把所有内容塞进 context**。

| 你的场景 | 必读 | 选读 |
|---|---|---|
| 简单的按钮 + 状态卡片 | 本文件即可 | - |
| 多组件面板(仪表盘、监控) | 本文件 + [components.md](references/components.md) | [data-binding.md](references/data-binding.md) |
| 数据绑定 + 增量更新 | 本文件 + [data-binding.md](references/data-binding.md) | [scripts.md](references/scripts.md) |
| 带按钮点击交互 | 本文件 + [events.md](references/events.md) | - |
| 长任务(>1Hz 刷新) | 本文件 + [scripts.md](references/scripts.md) | [data-binding.md](references/data-binding.md) |
| 写出来发现 UI 不工作 | [limits.md](references/limits.md) | [implementations.md](references/implementations.md) |
| 设计阶段确认 UI 质量 | - | [best-practices.md](references/best-practices.md) |

**判断不出该读哪个** → 看 [routing.md](references/routing.md) 的完整决策树。

## When to use this skill

**Use when**: 构建仪表盘/监控面板、交互式操作面板(按钮/表单/向导)、结构化可视化(卡片/网格/状态指示器)、增量更新。

**Do NOT use**: 单轮问答、需复制粘贴的内容、不支持 `a2ui_render` 的客户端、极简单次性输出。完整判断见 [limits.md](references/limits.md)。

## 核心规则(最少必要知识)

### 4 种消息类型

```json
{"messages": [
  {"createSurface":    {"surfaceId": "main", "catalogId": "cteno/v1"}},
  {"updateComponents": {"surfaceId": "main", "components": [...]}},
  {"updateDataModel":  {"surfaceId": "main", "data": {...}}},
  {"deleteSurface":    {"surfaceId": "main"}}
]}
```

| 消息 | 何时用 |
|---|---|
| `createSurface` | 首次渲染(必须) |
| `updateComponents` | 结构变化(增/删组件) |
| `updateDataModel` | **纯数据变化**(指标/状态/进度),更省 token |
| `deleteSurface` | 销毁渲染面 |

### 组件引用机制

- 所有组件以**扁平数组**传输(不在嵌套 JSON 里)
- 通过 `children: ["子组件ID1", "子组件ID2"]` 引用
- ID 匹配即替换,新 ID 则追加(增量更新机制)

### 数据绑定语法(关键省 token 手段)

组件中用 `${path.to.field}` 引用 dataModel 字段:

```json
{"id": "followers", "component": "MetricCard",
 "value": "${stats.followers}", "label": "粉丝数"}
```

后续只发 `updateDataModel` 即可(不用重发组件 schema)。**典型省 30-85% token**(视场景)。详见 [data-binding.md](references/data-binding.md)。

### 最常用的 5 个组件

完整 19 个组件见 [components.md](references/components.md)。最常用 5 个:

| 组件 | 用途 |
|---|---|
| `Container` | 根容器(必填) |
| `Card` | 分组卡片 |
| `MetricCard` | 单个指标 |
| `MetricsGrid` | 多个指标(自动布局) |
| `Button` | 交互按钮 |

### Action 事件(按钮点击 → Agent 闭环)

按钮加 `action` 字段,用户点击时 Agent 收到:

```
[User Action] {"surfaceId":"main","componentId":"btn-run","event":{"name":"start_experiment"}}
```

完整事件处理流程见 [events.md](references/events.md)。

### 推荐工作流:业务数据 → A2UI JSON

别手写 JSON。用本 skill 提供的脚本:

```bash
# 首屏
python scripts/a2ui_render.py initial --title "看板" --metric "A=1" -o snap.json

# 增量(自动算最小 diff,省 token)
python scripts/a2ui_diff.py --prev snap.json --next snap_new.json -o diff.json
```

完整脚本用法 + Python API + 测试见 [scripts.md](references/scripts.md)。

### 快速开始:复用模板

`templates/` 下有 5 个可直接填充的 JSON 模板,按场景选用:

| 模板 | 适用场景 |
|---|---|
| `empty-surface.json` | 空白渲染面占位 |
| `dashboard.json` | 通用看板/监控(支持 `{{PLACEHOLDER}}` 填充) |
| `monitor-panel.json` | 监控 + 清单(指标 + 活动) |
| `ci-pipeline-monitor.json` | CI/CD 流水线(含 `action_handlers`) |
| `interactive-panel.json` | 交互面板(按钮 + 表单) |

先 `cat templates/dashboard.json` 看结构,替换占位符即可上手。

## 设计原则

- **优先用复合组件**:`MetricsGrid`(自动布局)> 多个 `MetricCard`
- **结构变化用 updateComponents,数据变化用 updateDataModel**
- **更新频率 ≤5 秒/次**(更高频用 WebSocket 旁路,不要走 A2UI)
- **语义化 ID**:`"followers-metric"` 比 `"comp-1"` 好(diff 时好匹配)

更多设计原则见 [best-practices.md](references/best-practices.md)。

## 失败排查

| 现象 | 看哪里 |
|---|---|
| UI 完全不显示 | [implementations.md](references/implementations.md) - 确认客户端有 A2UI 渲染器 |
| 组件渲染异常 | [limits.md](references/limits.md) - 容错行为段 |
| 增量更新没生效 | [data-binding.md](references/data-binding.md) - 路径引用 |
| 按钮点击无反应 | [events.md](references/events.md) - 事件格式 |
| 不确定 A2UI 是否合适 | [limits.md](references/limits.md) - 不适用场景段 |