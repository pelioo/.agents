# 辅助脚本使用指南

本 skill 提供 CLI 脚本，把"业务数据 → A2UI JSON"的脏活自动化。Agent **不必手写 JSON 骨架**。

---

## 决策：手写 JSON vs 调用脚本

| 场景 | 推荐 | 原因 |
|---|---|---|
| Agent 能调 `a2ui_render` 工具，直接传 JSON | 手写或模板填充 | 一步到位 |
| Agent 只能输出文本/文件 | **调用 `a2ui_render.py`** | 脚本处理所有协议细节 |
| 高频增量更新（>1 次/分钟） | **调用 `a2ui_diff.py`** | 自动算最小更新，省 30-60% tokens |
| 单次一次性输出 | 手写 | 脚本启动开销不值得 |
| 极复杂自定义组件树 | 手写 | 脚本只覆盖常见模式 |

**核心收益**：
- Agent 不用记 14 个组件的属性 schema
- 不用关心 `createSurface` / `updateComponents` / `updateDataModel` 哪个该用
- 不用手写语义化组件 ID
- 增量更新场景自动算最小 diff（**实测节省 30-60% tokens**）

---

## `a2ui_render.py` — 业务数据 → A2UI JSON

**位置**：`scripts/a2ui_render.py`

### 首次渲染

```bash
python scripts/a2ui_render.py initial \
  --title "抖音涨粉看板" \
  --metric "粉丝数=5172" \
  --metric "目标=10000" \
  --progress "0.52" \
  --activity "10:30|完成竞品分析" \
  --output initial.json
```

输出包含 `createSurface` + `updateComponents` + `updateDataModel` 三件套。

### 增量更新

```bash
python scripts/a2ui_render.py update \
  --progress "0.67" \
  --metric "粉丝数=5891" \
  --output update.json
```

输出只包含 `updateDataModel`。

### 参数说明

| 参数 | 格式 | 说明 |
|---|---|---|
| `--title` | 字符串 | Card 标题（initial 必填） |
| `--metric` | `label=value` | 指标，可重复（≥2 个时自动用 MetricsGrid） |
| `--progress` | 0.0-1.0 | 进度值 |
| `--progress-label` | 字符串 | 进度标签（默认"总进度"） |
| `--activity` | `time\|text` | 活动条目，可重复 |
| `--status` | active/idle/error | 状态指示器值 |
| `--status-text` | 字符串 | 状态显示文本 |
| `--output` / `-o` | 文件路径 | 输出文件（默认 stdout） |
| `--stats` | flag | 把 payload 字节数/token 数打到 stderr |

---

## `a2ui_diff.py` — 两次数据快照 → 最小增量

**位置**：`scripts/a2ui_diff.py`

### 典型工作流

```bash
# T0: 渲染初始面板
python scripts/a2ui_render.py initial --title "Dashboard" \
  --metric "A=1" --metric "B=2" --output snap_t0.json

# T1: 渲染更新（也存为 snapshot）
python scripts/a2ui_render.py update --metric "A=99" --output snap_t1.json

# 算 diff（snap_t0 → snap_t1）
python scripts/a2ui_diff.py --prev snap_t0.json --next snap_t1.json \
  --output diff.json --stats
# 输出: [stats] diff=18t full=27t saved=33.3%
```

### 参数说明

| 参数 | 说明 |
|---|---|
| `--prev` | 之前的数据/messages 文件 |
| `--next` | 当前的数据/messages 文件 |
| `--surface` | Surface ID（默认 `main`） |
| `--output` / `-o` | 输出文件 |
| `--stats` | 显示节省比例 |
| `--quiet-no-change` | 无变化时静默退出（默认会打印提示） |

**输入格式自动识别**：纯数据 dict、`{"messages": [...]}` 包装、纯 messages 列表都能识别。

---

## Python API（直接调用）

如果 Agent 在 Python 进程中运行，可直接 import：

```python
from scripts.a2ui_core import render_initial, render_incremental, diff_data

# 首屏
payload = render_initial(
    title="抖音涨粉看板",
    metrics={"粉丝数": 5172, "目标": 10000},
    progress=0.52,
)

# 更新
update = render_incremental(progress=0.67, metrics={"粉丝数": 5891})

# Diff（自己保留 prev 快照时）
import json
prev_data = json.loads(open("snap_t0.json").read())["messages"][-1]["updateDataModel"]["data"]
next_data = update["messages"][0]["updateDataModel"]["data"]
diff = diff_data(prev_data, next_data)  # None = 无变化
```

---

## 测试

36 个测试覆盖：渲染正确性、UTF-8 round-trip、diff 算法各种场景、性能基准：

```bash
python -m unittest discover -s tests
```

实测 benchmark（来自 `test_bench.py`）：

```
[bench] 10 metrics, 1 changed: full=72t diff=29t saved=59.7%
[bench] progress only:             full=50t diff=22t saved=56.0%
[bench] no change:                 full=27t diff=0t  saved=100.0%
[bench] all changed (worst case):  full=50t diff=31t saved=38.0%
```

---

## 什么时候不用脚本

- 单个静态组件（如只输出一个 StatusIndicator）→ 直接 `updateComponents` 更轻
- 复杂自定义 children 嵌套（脚本只生成标准 3 层结构）→ 手写
- 不需要 diff 优化的场景（≤2 个字段更新）→ 直接写 `updateComponents` 也行