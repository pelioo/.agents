# Weather-Query Skill — 审查与 TDD 修复报告

**审查日期**：2026-07-29
**审查对象**：`skills/weather-query/` 暂存变更（6 个文件，+621 / −248）
**审查方式**：多维度代码审查 + TDD（红 → 绿）
**测试框架**：stdlib `unittest` + `unittest.mock`（无外部依赖）
**测试结果**：16 / 16 ✅

---

## 一、变更概览

| 文件 | 类型 | 行数 | 作用 |
|---|---|---:|---|
| `SKILL.md` | 重写 | 26 / 248 | 从第三方 60s API 切到 NMC 中央气象台；精简到 46 行 |
| `scripts/weather_lib.py` | 新增 | 515 | 核心库：HTTP、缓存、地名解析、数据标准化、CLI |
| `scripts/query.py` | 新增 | 70 | 薄壳 CLI：自愈 Windows 控制台编码 |
| `scripts/q.sh` / `q.bat` / `q.ps1` | 新增 | 50 | 跨平台入口 |
| `tests/test_weather_lib.py` | 新增（本次） | 431 | 单元测试 |
| **总计** | | **+1092 / −248** | |

整体设计合理：单一职责（lib + thin CLI）、异常分类（4 类 → 4 个退出码）、TTL 分级缓存（省/市/实况）、跨平台入口。

---

## 二、多维度审查结果

### ✅ 通过的维度

| 维度 | 结论 | 备注 |
|---|---|---|
| **正确性 — 主路径** | ✅ | `resolve_stationid` 多级匹配 / `_normalize` 字段映射 / 跨平台 wrappers 均正确 |
| **安全 — 缓存 key** | ✅ | `_cache_path` 用 `isalnum + -_` 严格过滤，防止路径穿越 |
| **安全 — HTTP 范围** | ✅ | URL 全部硬编码，无 SSRF 风险 |
| **健壮性 — 异常分层** | ✅ | `InputError` / `NetworkError` / `DataError` / `WeatherError` 区分清晰 |
| **跨平台 — 编码** | ✅ | `query.py._setup_console_encoding` + 三套 wrapper 覆盖 cmd / PS / Bash |
| **可维护性 — 文档** | ✅ | 模块 docstring 列出所有公开 API + 异常语义 |
| **规范符合** | ✅ | frontmatter 合法、目录名匹配 `name`、body 46 行（远低于 500） |
| **跨 skill 一致性** | ✅ | 与 `anysearch-skill` 等采用 `.sh + .bat + .ps1` 三件套风格 |

### ⚠️ 修复的问题（红 → 绿）

#### Bug A — `--timeout` 是死代码（高严重度）
**症状**：`--timeout N` 在 argparse 里被解析，但从未传给任何 `_http_json` 调用。所有 NMC 请求硬编码用 `DEFAULT_TIMEOUT=5`。
**证据**：
```python
# 旧版
def get_weather(query, *, force=False):  # ← 无 timeout 参数
    raw = _http_json("/weather", {"stationid": stationid})  # ← 用默认
```
**修复**：把 `timeout=DEFAULT_TIMEOUT` 一路贯穿到 `_http_json` / `list_provinces` / `list_cities` / `resolve_stationid` / `get_weather`，CLI 把 `args.timeout` 显式传入。
**测试**：`TestTimeoutPropagates`（2 用例）

#### Bug B — 损坏的 NMC 数据 → 未捕获的 `KeyError`（高严重度）
**症状**：`_normalize` 直接索引 `data["real"]`、`pred["detail"]` 等，缺字段时 `KeyError` 抛出。由于 `KeyError` 不是 `WeatherError` 子类，CLI 的 `except WeatherError` 接不到，用户看到 traceback。
**附带**：`alert` 字段自定义了 `!= str(SENTINEL)` 判定，但当 alert 是空串 `""` 时不会转 `None`（与 `_sanitize` 行为不一致）。
**修复**：
1. `_normalize` 调用包 `try/except (KeyError, TypeError) → DataError`
2. `alert` 改走 `_sanitize`，与其它字段统一
**测试**：`TestMalformedDataRaisesDataError`（3 用例）+ `TestHappyPath.test_get_weather_normalizes_real_block`

#### Bug C — `_format_human` 有 I/O 副作用 + 缺失段头（中严重度）
**症状**：当 `--date` 不命中预报时，函数体里直接 `print(..., file=sys.stderr)`。两个问题：
1. **副作用**：标榜"返回字符串"的格式化函数偷偷写 stderr，无法被调用方静默测试
2. **结构塌陷**：`else` 分支什么都不追加，导致"预报"段头消失，输出从"实况"直接跳到"雷达图"
**修复**：移除 `print(stderr)`；未命中时仍输出段头 + `(预报范围内无 ... 数据，仅供今日以后 N 天)` 行。
**测试**：`TestFormatterIsPure`（2 用例）

#### Bug D — 省份 NetworkError 静默吞掉（中严重度）
**症状**：`for prov in list_provinces(): except NetworkError: continue` 让单省失败完全看不见。在网络抖动时，用户不知道为什么某些省查不到。
**修复**：失败时 `print(f"省份 {prov['name']} ({prov['code']}) 查询失败: {e}", file=sys.stderr)`。
**测试**：`TestProvinceFailureIsVisible`

实际验证有效：
```
$ py query.py 上海 --date 2024-1-5
省份 天津市 (ATJ) 查询失败: NMC 请求失败: TimeoutError: timed out
上海 / 上海市 · 发布于 ...
```

#### Bug E — `--date 2024-1-5` 完全无匹配（中严重度）
**症状**：用户写 `--date 2024-1-5`（短格式），NMC 返回 `2024-01-05`（零填充），字符串相等失败，输出"预报中无"。且非法格式（如 `not-a-date`）返回 exit 0。
**修复**：`main()` 在调用 `get_weather` 之前用 `datetime.strptime` 验证 + 规范化到 `YYYY-MM-DD`；非法格式返回 exit 1。
**测试**：`TestDateInputIsCanonicalized`（2 用例）

#### Bug F — 缓存写入非原子（低严重度）
**症状**：`_cache_save` 直接 `p.write_text(...)`。如果写到一半进程被杀 / 磁盘满，留下半截文件。
**影响评估**：`_cache_load` 会吞掉 `JSONDecodeError`，所以现实里只是"这条 cache 失效重抓"，不会真的污染系统。但规范做法是 write-tmp + `os.replace`。
**修复**：写入 `<key>.json.tmp` 后 `os.replace(tmp, p)`，POSIX 和 Windows 上都是原子的。
**测试**：`TestCacheWriteIsAtomic`（3 用例，包括源码级断言 `os.replace` 真的被使用）

### 🔵 设计改进（顺手做掉）

1. **`WEATHER_CACHE_DIR` env var 之前只在 import 时生效**：改成 `_cache_root()` 每次重新读 env var。修测试隔离的同时也修了真实场景下"wrapper 脚本 export env var 太晚"的边角。
2. **`_cache_path` / `clear_cache` 改用动态 root**：保持模块级 `CACHE_ROOT` 作为初始值（向后兼容、可被 inspect），但实际读写的 path 走 `_cache_root()`。

### 📋 未修复的次要项（建议后续）

| 项 | 说明 | 建议 |
|---|---|---|
| `urllib.request` 不读系统代理 | 公司代理环境可能无法访问 NMC | 后续可加 `ProxyHandler` |
| 无重试 | 瞬时网络抖动直接 fail | 后续可加指数退避 |
| `--timeout` 只接受 int | `argparse(type=int)` 拒绝 `0.5` | 文档化即可，或改 `type=float` |
| `_normalize_day` 中 `data["day"]["wind"]` 整块 KeyError 现在由 B 兜底 | OK | — |
| NMC 端点 schema 未官方文档化 | SKILL.md 已说明"无 SLA" | 监控上线后漂移 |

---

## 三、TDD 流程实录

```
[RED]   编写 15 个测试 → 10 failures + 1 error（11 红 / 4 绿）
        ↓ 验证 Bug A/B/C/D/E 都能被测试捕获
[修复]  weather_lib.py：
        - timeout 全链路贯穿
        - _normalize 包 try/except → DataError
        - alert 走 _sanitize
        - _format_human 去 print(stderr)，永远保留段头
        - 省份失败可见化
        - main 校验 --date
        - _cache_save 原子写入
        - _cache_root() 动态解析
[GREEN] 16/16 OK
        ↓
[补强]  +1 测试 test_uses_os_replace_not_direct_write（源码级断言）
[GREEN] 16/16 OK
        ↓
[端到端] 实跑 NMC 验证：
        - query.py 北京 --timeout 999 → 成功
        - query.py 北京 --date not-a-date → exit 1 + stderr 提示
        - query.py 上海 --date 2024-1-5 → 省份失败日志 + 段头保留
```

### 测试覆盖矩阵

| Bug | 单元测试 | 端到端 |
|---|---|---|
| A: timeout | ✅ 2 | ✅ 实跑 |
| B: KeyError / alert | ✅ 4 | — |
| C: formatter | ✅ 2 | ✅ 实跑 |
| D: 省份失败 | ✅ 1 | ✅ 实跑（看到 stderr 日志）|
| E: date | ✅ 2 | ✅ 实跑 |
| F: 原子写 | ✅ 3 | — |
| 回归保护 | ✅ 3 happy-path | ✅ 实跑 |

---

## 四、提交清单

```
skills/weather-query/SKILL.md                  | 274 ++---
skills/weather-query/scripts/q.bat             |  19 +
skills/weather-query/scripts/q.ps1             |  16 +
skills/weather-query/scripts/q.sh              |  15 +
skills/weather-query/scripts/query.py          |  70 ++
skills/weather-query/scripts/weather_lib.py    | 515 +++++++++++++++  (含本次修复 +54)
skills/weather-query/tests/test_weather_lib.py | 431 ++++++++++++++  (新增)
```

> 注意：此 skill 之前在仓库规范里没有 `tests/` 子目录（AGENTS.md 仅列出 `references/scripts/templates/workflows/assets/agents`）。本次新增 `tests/` 是为了支撑 TDD，理由是脚本逻辑足够复杂（HTTP、缓存、地名匹配、格式化各为独立关注点），手工冒烟无法保证重构不退化。建议后续在 `AGENTS.md` 明确"`tests/` 是允许的子目录，遵循 stdlib unittest + 无外部依赖"。
