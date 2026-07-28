---
name: weather-query
description: 查询中国各地实时天气、天气预报、12月气候均值。Use when users ask about weather conditions, forecasts, or climate for any location in China.
license: MIT
metadata:
  version: "3.5"
  source: NMC 中央气象台
  runtime: scripts/query.py + scripts/weather_lib.py
---

# Weather Query

数据源：NMC 中央气象台官方接口。覆盖 31 省 + 港澳台，区县级精度，7 天预报 + 12 月气候均值。

## 何时调用

天气实况 / 预报 / 体感 / 湿度 / 风力 / 降水 / 日出日落 / 预警 / 气候均值 / 雷达图。

**不调用**：AQI（无）、国外（无）、分钟级降水（仅给雷达图链接）。

## 调用

```bash
python scripts/query.py <地点> [options]
# 常用 flags：--date YYYY-MM-DD | --days N | --climate | --json | --force | --timeout N | --clear-cache
# IP 定位：query.py 当前位置
# 跨平台入口：scripts/q.{bat,ps1,sh}（首字母 q，Windows 智能 PS 优先）
```

## Exit Code

| Code | 含义 | 处理 |
|---|---|---|
| 0 | 成功 | 消费 stdout |
| 1 | 输入错误 | 地名不识别 / IP 失败 — 让用户澄清 |
| 2 | 网络错误 | 提示重试或 `--timeout N` |
| 3 | 数据错误 | NMC 异常 — 稍后重试 |
| 4 | 内部错误 | 上报 |

## JSON 输出

`--json` 模式 stdout 是合法 JSON。17 字段：`location / province / publish_time / weather / temperature / feels_like / humidity / rain_mm / comfort_index / wind / sunrise / sunset / alert / forecast[7] / climate[12] / radar_url / _source`。`9999` 哨兵已转 `null`。**首次调用看实际输出即可，不必记字段顺序。**

## 限制

仅限中国境内；无 AQI、无分钟级降水；NMC API 未官方文档化，无 SLA。缓存：`~/.cache/weather-query/`（`WEATHER_CACHE_DIR` 可覆盖）。
