# A2UI 数据绑定（updateDataModel）

`updateDataModel` 是 A2UI 协议中**最省带宽**的更新机制：只发送数据，不发送组件定义。组件通过 `${path}` 语法引用 dataModel 字段，前端自动响应式更新。

---

## 何时使用 updateDataModel vs updateComponents

| 场景 | 推荐 | 原因 |
|---|---|---|
| 组件结构不变，只改数值 | ✅ `updateDataModel` | 带宽最小（~30 tokens） |
| 需要新增/删除组件 | ✅ `updateComponents` | dataModel 无法表达结构变化 |
| 周期性高频刷新（>1Hz） | ✅ `updateDataModel` | 避免反复重发组件 schema |
| 一次性全屏初始化 | ✅ `updateComponents`（含 `createSurface`） | 必须先建立组件树 |
| 改组件样式（variant、color 等） | ✅ `updateComponents` | 样式不在 dataModel 范围 |

**经验法则**：
- **结构变化**（增/删组件、改 children）→ `updateComponents`
- **纯数据变化**（指标数字、状态值、进度）→ `updateDataModel`
- 两者配合：初始化用 `updateComponents` 一次，后续纯数据更新走 `updateDataModel`

---

## 引用语法

组件属性中通过 `${dataModel.path.to.field}` 引用 dataModel 字段：

```json
// 创建组件时，引用 dataModel 字段
{"id": "followers", "component": "MetricCard", "value": "${stats.followers}", "label": "粉丝数"}
{"id": "progress", "component": "Progress", "value": "${progress.value}", "label": "${progress.label}"}
{"id": "status", "component": "StatusIndicator", "status": "${system.status}", "text": "${system.message}"}
```

**路径规则**：

- 用 `.` 分层访问嵌套对象
- 顶层字段直接写名字（如 `${score}`）
- 不存在的路径渲染为空字符串或默认值（前端容错）
- 字符串模板可以混用字面量（如 `"粉丝: ${stats.followers}"`）

---

## 完整示例：监控仪表盘的两种更新模式

### 首次渲染（createSurface + updateComponents）

```json
{"messages": [
  {"createSurface": {"surfaceId": "main", "catalogId": "cteno/v1"}},
  {"updateComponents": {"surfaceId": "main", "components": [
    {"id": "root", "component": "Container", "children": ["card"]},
    {"id": "card", "component": "Card", "title": "系统监控", "children": ["metrics"]},
    {"id": "metrics", "component": "Row", "gap": 12, "children": ["mc-cpu", "mc-mem", "mc-net"]},
    {"id": "mc-cpu", "component": "MetricCard", "value": "${cpu.usage}", "label": "CPU 使用率", "trend": "${cpu.trend}", "trendDirection": "${cpu.direction}"},
    {"id": "mc-mem", "component": "MetricCard", "value": "${mem.usage}", "label": "内存使用率", "trend": "${mem.trend}", "trendDirection": "${mem.direction}"},
    {"id": "mc-net", "component": "MetricCard", "value": "${net.throughput}", "label": "网络吞吐", "trend": "${net.trend}", "trendDirection": "${net.direction}"},
    {"id": "progress", "component": "Progress", "value": "${deploy.progress}", "label": "${deploy.stage}"}
  ]}},
  {"updateDataModel": {"surfaceId": "main", "data": {
    "cpu": {"usage": "42%", "trend": "+2%", "direction": "up"},
    "mem": {"usage": "6.8GB", "trend": "stable", "direction": "up"},
    "net": {"throughput": "1.2Gbps", "trend": "+100Mbps", "direction": "up"},
    "deploy": {"progress": 0.42, "stage": "正在部署到生产环境"}
  }}}
]}
```

### 数据更新（30 秒后）

**方式 A：`updateDataModel`（推荐，最省带宽）**

```json
{"messages": [
  {"updateDataModel": {"surfaceId": "main", "data": {
    "cpu": {"usage": "45%", "trend": "+5%", "direction": "up"},
    "mem": {"usage": "7.1GB", "trend": "+0.3GB", "direction": "up"},
    "net": {"throughput": "1.4Gbps", "trend": "+200Mbps", "direction": "up"},
    "deploy": {"progress": 0.58, "stage": "正在运行健康检查"}
  }}}
]}
```

体积：~280 bytes / ~75 tokens

**方式 B：`updateComponents`（备选，必须改组件属性时用）**

```json
{"messages": [
  {"updateComponents": {"surfaceId": "main", "components": [
    {"id": "mc-cpu", "component": "MetricCard", "value": "45%", "label": "CPU 使用率", "trend": "+5%", "trendDirection": "up"},
    {"id": "mc-mem", "component": "MetricCard", "value": "7.1GB", "label": "内存使用率", "trend": "+0.3GB", "trendDirection": "up"},
    {"id": "mc-net", "component": "MetricCard", "value": "1.4Gbps", "label": "网络吞吐", "trend": "+200Mbps", "trendDirection": "up"},
    {"id": "progress", "component": "Progress", "value": 0.58, "label": "正在运行健康检查"}
  ]}}
]}
```

体积：~720 bytes / ~200 tokens

**对比**：`updateDataModel` 比 `updateComponents` 节省约 **60-70% 带宽**。

---

## 常见陷阱

1. **dataModel 不能改变组件结构**
   - 想新增组件 / 改 children 列表 → 必须用 `updateComponents`
   - dataModel 只能更新"已经存在"的组件引用的字段

2. **路径写错不会报错**
   - `${stats.followres}`（拼写错误）渲染为空，前端静默失败
   - 建议在 Agent 端先用本地对象校验路径，再下发

3. **嵌套对象必须传完整子树**
   - `updateDataModel.data` 是**合并**而非**替换**
   - 但如果你传 `{"cpu": {"usage": "50%"}}`，旧的 `cpu.trend` / `cpu.direction` 保留
   - 想完全替换某子树，传完整对象

4. **首次渲染建议同时下发 dataModel**
   - 在第一个 `messages` 数组里把 `createSurface` + `updateComponents` + `updateDataModel` 一起发
   - 避免组件先渲染默认值（空字符串 / 0）再被 dataModel 替换的闪烁

5. **高频更新不要超 5 秒一次**
   - 即使走 dataModel，前端仍按 React 渲染，过快会卡顿
   - 真正高频（>1Hz）的数据流建议用 WebSocket 旁路，不走 A2UI

---

## 何时**不要**用数据绑定

| 场景 | 原因 |
|---|---|
| 一次性初始化 | 字段数量 ≤5 且不会刷新 → 直接写在 updateComponents 里更简单 |
| 客户端不支持 dataModel | 极少数旧客户端只识别 updateComponents → 降级处理 |
| 数据来源是用户输入 | 表单值通常直接绑定组件 state，不走 dataModel |