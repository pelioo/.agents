"""NMC Weather Query Library — 中国天气查询核心库

数据源：中央气象台（NMC）官方公开接口
- 端点：http://www.nmc.cn/rest/*
- 编码：UTF-8
- 鉴权：无需

公开 API：
- get_weather(query, *, force=False) -> dict   主入口
- resolve_stationid(query) -> (stationid, city, province)
- list_provinces() / list_cities(pcode)
- clear_cache()

异常类（按错误类型区分，调用方可分别处理）：
- InputError    — 用户输入错误（地名找不到 / 参数错）        exit 1
- NetworkError  — 网络错误（超时 / 连接失败 / 5xx）          exit 2
- DataError     — 数据错误（服务端返回空 / 解析失败）        exit 3
- WeatherError  — 其他内部错误                              exit 4

跨平台：
- 仅依赖 Python 3.8+ 标准库
- 缓存路径：~/.cache/weather-query/ （可通过 WEATHER_CACHE_DIR 环境变量覆盖）
- 文件 I/O 显式 UTF-8
"""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://www.nmc.cn/rest"
DEFAULT_TIMEOUT = 5
SENTINEL = 9999

# Best-effort initial cache root for inspection. Real cache lookups go through
# _cache_root() so WEATHER_CACHE_DIR set after import (tests, late-binding
# wrappers) is honored.
CACHE_ROOT = Path(os.environ.get("WEATHER_CACHE_DIR", Path.home() / ".cache" / "weather-query"))
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

TTL_PROVINCE = 86400      # 24 小时 — 省份列表极少变
TTL_CITY = 86400          # 24 小时 — 城市列表稳定
TTL_WEATHER = 600         # 10 分钟 — 实况更新频次


def _cache_root():
    """Re-resolve cache root from env var each call (lazy).

    Why lazy: tests set WEATHER_CACHE_DIR in setUp(), and any user code that
    mutates the env var post-import should still get the new path.
    """
    env = os.environ.get("WEATHER_CACHE_DIR")
    p = Path(env) if env else CACHE_ROOT
    p.mkdir(parents=True, exist_ok=True)
    return p


# ============== 异常类 ==============

class WeatherError(Exception):
    """所有 skill 内异常的基类"""

class InputError(WeatherError):
    """用户输入错误：地名找不到、参数为空、地名仅含行政区划字等"""

class NetworkError(WeatherError):
    """网络错误：超时、连接失败、HTTP 5xx 等"""

class DataError(WeatherError):
    """数据错误：服务端返回空、JSON 解析失败、字段缺失等"""


# ============== HTTP ==============

def _http_json(path, params=None, timeout=DEFAULT_TIMEOUT):
    """GET 一个 NMC 端点并返回 dict。失败抛 NetworkError / DataError。"""
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "weather-query/3.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        raise NetworkError(f"NMC 请求失败: {type(e).__name__}: {e}") from e
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DataError(f"NMC 响应编码异常（非 UTF-8）: {e}") from e
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise DataError(f"NMC 响应解析失败: {e}") from e


# ============== 哨兵值处理 ==============

def _sanitize(v):
    """NMC 哨兵值 9999 / '9999' / '' / '-' → None"""
    if v in (SENTINEL, str(SENTINEL), "", "-"):
        return None
    return v


def _fmt_v(v, unit=""):
    """人类可读格式化：None → '-'，否则 str(v) + 可选单位"""
    if v is None:
        return "-"
    return f"{v}{unit}"


# ============== 文件缓存 ==============

def _cache_path(category, key):
    """category: 'provinces' / 'cities' / 'weather'"""
    root = _cache_root()
    p = root / category
    p.mkdir(parents=True, exist_ok=True)
    # key 只允许字母数字 / 短横线 / 下划线，避免路径穿越
    safe = "".join(c for c in key if c.isalnum() or c in ("-", "_"))
    return p / f"{safe}.json"


def _cache_load(category, key, ttl):
    p = _cache_path(category, key)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > ttl:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _cache_save(category, key, data):
    """Atomic write: tmp file → os.replace. Crash mid-write leaves the old
    cache file untouched instead of a half-written corrupt one."""
    p = _cache_path(category, key)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def clear_cache():
    """删除所有缓存文件并重建空目录。"""
    root = _cache_root()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


# ============== 步骤 1：定位 stationid ==============

def list_provinces(force=False, *, timeout=DEFAULT_TIMEOUT):
    """返回所有省份 [{code, name, url}]"""
    if not force:
        cached = _cache_load("provinces", "all", TTL_PROVINCE)
        if cached is not None:
            return cached
    data = _http_json("/province/all", timeout=timeout)
    _cache_save("provinces", "all", data)
    return data


def list_cities(pcode, force=False, *, timeout=DEFAULT_TIMEOUT):
    """返回某省下所有城市/区县 [{code, province, city, url}]"""
    if not force:
        cached = _cache_load("cities", pcode, TTL_CITY)
        if cached is not None:
            return cached
    data = _http_json(f"/province/{pcode}", timeout=timeout)
    _cache_save("cities", pcode, data)
    return data


def resolve_stationid(query, *, timeout=DEFAULT_TIMEOUT):
    """中文地名 → (stationid, city, province)

    匹配优先级：
      100 — city 与 query 或 normalized 完全相等
       80 — normalized 是 city 的子串（"海淀" in "海淀区"）
       60 — city 是 normalized 的子串（"杭州" in "杭州西湖"），diff ≤ 3

    失败抛 InputError。
    """
    if query is None:
        raise InputError("地名不能为空")
    if not isinstance(query, str):
        raise InputError(f"地名必须是字符串，收到: {type(query).__name__}")
    query = query.strip()
    if not query:
        raise InputError("地名不能为空")

    # IP 定位兜底
    if query in ("当前位置", "这里", "我这里", "本地", "current", "ip"):
        pos = _http_json("/position", timeout=timeout)
        return pos["code"], pos["city"], pos["province"]

    # 多轮剥离行政区划后缀（处理"北京市海淀区"等多级行政区划）
    suffixes = ["市", "区", "县", "省", "自治州", "盟", "地区"]
    normalized = query
    for _ in range(len(suffixes)):
        stripped_once = False
        for s in suffixes:
            if normalized.endswith(s) and len(normalized) > len(s):
                normalized = normalized[:-len(s)]
                stripped_once = True
                break
        if not stripped_once:
            break

    if not normalized:
        raise InputError(f"地名仅含行政区划字、无有效主体: {query!r}")

    candidates = [normalized, query]
    matches = []

    # 遍历省份，单省 fetch 失败不应击穿整次查询
    for prov in list_provinces(timeout=timeout):
        try:
            cities = list_cities(prov["code"], timeout=timeout)
        except NetworkError as e:
            # 可见化：原来静默 continue，用户不知道为什么某些省打不到
            print(f"省份 {prov['name']} ({prov['code']}) 查询失败: {e}",
                  file=sys.stderr)
            continue
        for c in cities:
            city = c["city"]
            for cand in candidates:
                if city == cand:
                    matches.append((100, c["code"], city, prov["name"]))
                    break
                # 要求 cand 和 city 都 ≥ 2 字符，避免单字"区"/"市"误匹配
                if len(cand) >= 2 and len(city) >= 2 and cand in city:
                    matches.append((80, c["code"], city, prov["name"]))
                    break
                # 反向 substring：city 在 cand 里，差 ≤ 3 字符
                if len(cand) >= 2 and len(city) >= 2 and city in cand and len(cand) - len(city) <= 3:
                    matches.append((60, c["code"], city, prov["name"]))
                    break
            else:
                continue

    if not matches:
        raise InputError(f"找不到匹配地点: {query}")

    matches.sort(key=lambda m: -m[0])
    return matches[0][1], matches[0][2], matches[0][3]


# ============== 步骤 2：主接口 ==============

def get_weather(query, *, force=False, timeout=DEFAULT_TIMEOUT):
    """主入口：返回标准化 dict。

    Args:
        query: 中文地名 / '当前位置'
        force: True 忽略缓存
        timeout: HTTP 超时（秒）

    Returns:
        dict 包含 location, province, publish_time, weather, temperature,
        feels_like, humidity, rain_mm, comfort_index, wind, sunrise, sunset,
        alert, forecast[7], climate[12], radar_url

    Raises:
        InputError / NetworkError / DataError
    """
    stationid, city, province = resolve_stationid(query, timeout=timeout)

    if not force:
        cached = _cache_load("weather", stationid, TTL_WEATHER)
        if cached is not None:
            return cached

    raw = _http_json("/weather", {"stationid": stationid}, timeout=timeout)
    if not raw.get("data"):
        raise DataError(f"NMC 返回空数据: stationid={stationid}")

    try:
        normalized = _normalize(raw["data"], city, province)
    except (KeyError, TypeError) as e:
        # NMC 结构变化 / 字段缺失 — 转为 DataError 让上游 exit 3，而不是裸 KeyError traceback
        raise DataError(f"NMC 数据结构异常: 缺少字段 {e}") from e
    _cache_save("weather", stationid, normalized)
    return normalized


# ============== 数据标准化 ==============

def _normalize_day(d):
    def fmt_wind(direct, power):
        d_s = _sanitize(direct)
        p_s = _sanitize(power)
        parts = [p for p in [d_s, p_s] if p]
        return " ".join(parts) if parts else None

    return {
        "date": d["date"],
        "day": {
            "weather": _sanitize(d["day"]["weather"]["info"]),
            "temperature": _sanitize(d["day"]["weather"]["temperature"]),
            "wind": fmt_wind(d["day"]["wind"]["direct"], d["day"]["wind"]["power"]),
        },
        "night": {
            "weather": _sanitize(d["night"]["weather"]["info"]),
            "temperature": _sanitize(d["night"]["weather"]["temperature"]),
            "wind": fmt_wind(d["night"]["wind"]["direct"], d["night"]["wind"]["power"]),
        },
        "precipitation_mm": _sanitize(d["precipitation"]),
    }


def _normalize(data, city, province):
    real = data["real"]
    pred = data["predict"]
    return {
        "location": city,
        "province": province,
        "publish_time": real["publish_time"],

        # 实况
        "weather": _sanitize(real["weather"]["info"]),
        "temperature": _sanitize(real["weather"]["temperature"]),
        "feels_like": _sanitize(real["weather"]["feelst"]),
        "humidity": _sanitize(real["weather"]["humidity"]),
        "rain_mm": _sanitize(real["weather"]["rain"]),
        "comfort_index": _sanitize(real["weather"]["rcomfort"]),
        "wind": {
            "direct": _sanitize(real["wind"]["direct"]),
            "degree": _sanitize(real["wind"]["degree"]),
            "speed_ms": _sanitize(real["wind"]["speed"]),
            "power": _sanitize(real["wind"]["power"]),
        },
        "sunrise": real["sunriseSunset"]["sunrise"],
        "sunset": real["sunriseSunset"]["sunset"],
        "alert": _sanitize(real["warn"]["alert"]),

        # 预报
        "forecast": [_normalize_day(d) for d in pred["detail"]],

        # 气候均值
        "climate": [
            {"month": m["month"], "max_temp": m["maxTemp"],
             "min_temp": m["minTemp"], "precip": m["precipitation"]}
            for m in data.get("climate", {}).get("month", [])
        ],

        # 雷达图
        "radar_url": "http://www.nmc.cn" + data["radar"]["image"] if data.get("radar") else None,

        # 元数据
        "_source": "NMC 中央气象台",
        "_schema_version": "3.0",
    }


# ============== CLI 入口 ==============

def main():
    """当作为脚本运行时调用 query.py 的入口。"""
    import argparse
    from datetime import datetime

    p = argparse.ArgumentParser(
        prog="python query.py",
        description="中国天气查询（数据源：NMC 中央气象台）",
    )
    p.add_argument("location", nargs="?", help="中文地名 / '当前位置' (IP 定位)")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p.add_argument("--days", type=int, help="显示未来 N 天预报")
    p.add_argument("--date", metavar="YYYY-MM-DD", help="显示指定日期的预报")
    p.add_argument("--climate", action="store_true", help="显示 12 月气候均值")
    p.add_argument("--force", action="store_true", help="忽略缓存，强制刷新")
    p.add_argument("--clear-cache", action="store_true", help="清空本地缓存")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP 超时（秒）")
    args = p.parse_args()

    if args.clear_cache:
        clear_cache()
        print("缓存已清空", file=sys.stderr)
        return 0

    if not args.location:
        p.print_help()
        return 1

    # --date 验证 + 规范化：接受 "2024-1-5" 和 "2024-01-05"，统一存为后者的形式
    if args.date:
        try:
            dt = datetime.strptime(args.date, "%Y-%m-%d")
            args.date = dt.strftime("%Y-%m-%d")
        except ValueError:
            print(f"--date 格式错误（应为 YYYY-MM-DD）: {args.date}",
                  file=sys.stderr)
            return 1

    try:
        w = get_weather(args.location, force=args.force, timeout=args.timeout)
    except InputError as e:
        print(f"输入错误: {e}", file=sys.stderr)
        return 1
    except NetworkError as e:
        print(f"网络错误: {e}", file=sys.stderr)
        return 2
    except DataError as e:
        print(f"数据错误: {e}", file=sys.stderr)
        return 3
    except WeatherError as e:
        print(f"未知错误: {e}", file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(w, ensure_ascii=False, indent=2))
        return 0

    # 人类可读输出（美化版：字段对齐 + 段落分组 + 预报表格化）
    print(_format_human(w, args))
    return 0


def _format_human(w, args):
    """人类可读输出。

    设计原则：
    - label 固定 8 字符宽度（中英文混排对齐）
    - 段间空行 + 横线分组（实况 / 预报 / 雷达 / 气候）
    - 不用 emoji（cmd.exe GBK 风险）、不用 ASCII box（视觉重）
    - 预报合并"白天→夜间 + 温度区间 + 降水"为一行
    """
    sep = "─" * 50
    lines = []

    # === 头部：地点 / 省 / 发布时间 ===
    lines.append(f"{w['location']} / {w['province']} · 发布于 {w['publish_time']}")
    lines.append(sep)
    lines.append("")

    # === 实况 ===
    lines.append("实况")
    lines.append(f"  天气          {_fmt_v(w['weather'])}")
    lines.append(f"  温度          {_fmt_v(w['temperature'], '°C')} (体感 {_fmt_v(w['feels_like'], '°C')})")
    lines.append(f"  湿度          {_fmt_v(w['humidity'], '%')}")
    wind = f"{_fmt_v(w['wind']['direct'])} {_fmt_v(w['wind']['speed_ms'], ' m/s')} ({_fmt_v(w['wind']['power'])})"
    lines.append(f"  风力          {wind}")
    lines.append(f"  日出 / 日落   {w['sunrise'][-5:]} / {w['sunset'][-5:]}")
    lines.append(f"  舒适度        {_fmt_v(w['comfort_index'])}")
    lines.append(f"  预警          {w['alert'] if w['alert'] else '无'}")
    lines.append("")

    # === 气候均值（仅 --climate）===
    if args.climate:
        lines.append("12 月气候均值")
        lines.append(sep)
        for m in w["climate"]:
            lo = _fmt_v(m["min_temp"], "°C")
            hi = _fmt_v(m["max_temp"], "°C")
            lines.append(f"  {m['month']:>2}月  {lo} ～ {hi}   降水 {_fmt_v(m['precip'], 'mm')}")
        lines.append("")

    # === 预报 ===
    def _fmt_day(d):
        day_t = _fmt_v(d["day"]["temperature"], "°C")
        night_t = _fmt_v(d["night"]["temperature"], "°C")
        if day_t != "-" and night_t != "-":
            temp = f"{night_t} ～ {day_t}"
            temp_field = f"{temp:<14}"
        else:
            temp = day_t if day_t != "-" else night_t
            # 单端时只占 6 字符宽，避免 "25°C          " 这种大空格
            temp_field = f"  {temp:<10}" if temp != "-" else "            "
        return (f"  {d['date']}  白天 {_fmt_v(d['day']['weather'])} → 夜间 {_fmt_v(d['night']['weather'])}"
                f"   {temp_field}  降水 {_fmt_v(d['precipitation_mm'], 'mm')}")

    if args.date:
        target = args.date
        match = next((d for d in w["forecast"] if d["date"] == target), None)
        lines.append(f"预报 · {target}")
        lines.append(sep)
        if match:
            lines.append(_fmt_day(match))
        else:
            # 未命中也保留段头，输出结构稳定；调用方可检检测最后一段是否含 "(预报范围内无...)"
            lines.append(f"  (预报范围内无 {target} 数据，仅供今日以后 {len(w['forecast'])} 天)")
    elif args.days:
        n = min(args.days, len(w["forecast"]))
        lines.append(f"预报 · 未来 {n} 天")
        lines.append(sep)
        for d in w["forecast"][:n]:
            lines.append(_fmt_day(d))
    else:
        n = min(3, len(w["forecast"]))
        lines.append(f"预报 · 未来 {n} 天")
        lines.append(sep)
        for d in w["forecast"][:n]:
            lines.append(_fmt_day(d))
    lines.append("")

    # === 雷达图 ===
    if w.get("radar_url"):
        lines.append("雷达图")
        lines.append(sep)
        lines.append(f"  {w['radar_url']}")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())