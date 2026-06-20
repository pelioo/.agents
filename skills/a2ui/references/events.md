# Action 事件处理

按钮点击 → Agent 闭环的完整机制。

---

## 事件格式

按钮带 `action` 字段：

```json
{
  "id": "btn-run",
  "component": "Button",
  "label": "开始实验",
  "variant": "primary",
  "icon": "play",
  "action": {
    "event": {
      "name": "start_experiment",
      "data": {"experiment_id": 42}
    }
  }
}
```

`event.data` 是可选的附加数据，会原样传给 Agent。

---

## Agent 收到的消息

用户点击后，Agent 在下一次回复中会看到：

```
[User Action] {"surfaceId":"main","componentId":"btn-run","event":{"name":"start_experiment","data":{"experiment_id":42}}}
```

字段说明：

| 字段 | 来源 | 用途 |
|---|---|---|
| `surfaceId` | 创建 surface 时的 ID | 标识哪个渲染面 |
| `componentId` | Button 的 ID | 标识哪个按钮 |
| `event.name` | Button.action.event.name | 事件语义（必读） |
| `event.data` | Button.action.event.data | 附加参数（可选） |

---

## Agent 处理流程

```
收到 [User Action] 消息
│
├─ 解析 event.name 判断用户意图
│   例: "start_experiment" → 开始实验
│       "pause"           → 暂停
│       "refresh_data"    → 重新采集数据
│
├─ 可选: 读取 event.data 拿附加参数
│   例: data.experiment_id = 42
│
├─ 执行对应业务逻辑（开始实验 / 暂停 / 重新采集等）
│
└─ 用 updateComponents 或 updateDataModel 反馈结果
    例: status 改为 "running"、Progress 推到 50%、新指标展示
```

---

## 命名约定

事件名应该语义化，反映用户意图：

| 推荐 | 避免 |
|---|---|
| `start_experiment` | `click1` |
| `refresh_data` | `action` |
| `pause_monitoring` | `btn` |
| `step_select` | `next` |
| `submit_form` | `submit` |

**好处**：
- Agent 更容易理解意图（不需要查 componentId 映射表）
- 同一事件可被多个按钮触发（如"刷新"可放在工具栏 + 卡片里）
- 调试时容易追踪（看日志知道是哪个动作）

---

## 多按钮场景

用 `ButtonGroup` 组合多个按钮：

```json
{
  "id": "actions",
  "component": "ButtonGroup",
  "children": ["btn-run", "btn-pause", "btn-reset"]
}
```

Agent 需要根据 `event.name` 分别处理每个按钮。

---

## 状态联动：Action + StatusIndicator

典型模式：用户点击"开始"按钮 → Agent 把 StatusIndicator 改为 active：

```json
// 用户点击 btn-run，event.name = "start"
// Agent 回复:
//   1. 在业务逻辑里开始实验
//   2. 用 updateDataModel 刷新 status
{"messages": [
  {"updateDataModel": {"surfaceId": "main", "data": {
    "status": {"value": "active", "text": "运行中"},
    "progress": {"value": 0.0, "label": "初始化中"}
  }}}
]}
```

按钮的 `disabled` 状态通常需要 Agent 通过 `updateComponents` 替换整个 Button 组件来切换（如暂停时禁用"开始"按钮）。

---

## 错误处理

如果 Agent 收到未知 `event.name`：

1. 忽略该消息（不报错）
2. 在下一次回复中告知用户："收到未识别的动作"
3. 或主动读取 `[User Action]` 完整 payload 自行决定怎么处理

如果同一按钮被快速点击多次：每个点击都会生成独立的 `[User Action]` 消息，Agent 需要在业务逻辑层做幂等保护（如检查"实验是否已在运行"）。