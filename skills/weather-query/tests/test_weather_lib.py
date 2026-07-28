"""Tests for weather_lib — uses stdlib unittest + mock (no external deps).

Each test class corresponds to one bug found in the code review. Tests are
written first (TDD red), then the implementation is fixed to make them green.

Test data is intentionally minimal — only the fields _normalize() touches.
Real NMC responses are bigger, but the library's contract is "normalize what
we read; raise DataError if the shape is wrong."
"""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError

# Add scripts/ to sys.path so `import weather_lib` works regardless of cwd.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import weather_lib  # noqa: E402


# ---------- canned NMC fixtures ----------

PROVINCES = [
    {"code": "101010100", "name": "北京", "url": "/province/101010100"},
    {"code": "101020100", "name": "上海", "url": "/province/101020100"},
]

BEIJING_CITIES = [
    {"code": "101010100", "province": "北京", "city": "北京", "url": "/city/101010100"},
    {"code": "101010200", "province": "北京", "city": "海淀区", "url": "/city/101010200"},
]

SHANGHAI_CITIES = [
    {"code": "101020100", "province": "上海", "city": "上海", "url": "/city/101020100"},
]


def _ok_weather_payload():
    """A minimal-but-valid NMC /weather payload."""
    return {
        "data": {
            "real": {
                "publish_time": "2024-01-15 14:00",
                "weather": {"info": "晴", "temperature": "5",
                            "feelst": "2", "humidity": "45",
                            "rain": "0", "rcomfort": "凉"},
                "wind": {"direct": "东北风", "degree": "45",
                         "speed": "3", "power": "2级"},
                "sunriseSunset": {"sunrise": "2024-01-15 07:30",
                                  "sunset": "2024-01-15 17:15"},
                "warn": {"alert": ""},
            },
            "predict": {
                "detail": [
                    {"date": "2024-01-15",
                     "day": {"weather": {"info": "晴", "temperature": "8"},
                             "wind": {"direct": "北风", "power": "2级"}},
                     "night": {"weather": {"info": "多云", "temperature": "-2"},
                               "wind": {"direct": "北风", "power": "1级"}},
                     "precipitation": "0"},
                ],
            },
            "climate": {"month": [{"month": "1", "maxTemp": "3",
                                   "minTemp": "-7", "precipitation": "3"}]},
            "radar": {"image": "/radar/beijing.png"},
        }
    }


# ---------- HTTP mock helpers ----------

class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _make_route(responses):
    """responses: dict[substring-of-URL -> dict | Exception]."""
    def route(req, **kwargs):
        url = req.full_url
        for pattern, body in responses.items():
            if pattern in url:
                if isinstance(body, Exception):
                    raise body
                return _FakeResp(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        raise AssertionError(f"unexpected URL in test: {url}")
    return route


# ---------- base test case with isolated cache ----------

class _IsolatedCache(unittest.TestCase):
    """Each test gets a fresh temp cache dir so suites don't bleed.

    Note: weather_lib.CACHE_ROOT is bound at import time, so just setting
    WEATHER_CACHE_DIR in setUp() is not enough — we also patch the attribute.
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="wqlib-test-")
        self._old_cache_root = weather_lib.CACHE_ROOT
        new_root = Path(self._tmpdir)
        new_root.mkdir(parents=True, exist_ok=True)
        weather_lib.CACHE_ROOT = new_root

    def tearDown(self):
        weather_lib.CACHE_ROOT = self._old_cache_root


# ====================================================================
# Bug A: --timeout flag is parsed by CLI but never reaches HTTP layer
# ====================================================================

class TestTimeoutPropagates(_IsolatedCache):
    """Bug A: the --timeout CLI flag must reach the underlying HTTP calls."""

    def test_get_weather_accepts_and_uses_timeout_kwarg(self):
        captured = []

        def spy_http(path, params=None, timeout=weather_lib.DEFAULT_TIMEOUT):
            captured.append((path, params, timeout))
            # Return enough to short-circuit resolve_stationid and weather parse
            if path == "/province/all":
                return PROVINCES
            if path.startswith("/province/"):
                return BEIJING_CITIES
            if path == "/weather":
                return _ok_weather_payload()
            raise AssertionError(f"unexpected path {path}")

        with mock.patch.object(weather_lib, "_http_json", side_effect=spy_http):
            weather_lib.get_weather("北京", force=True, timeout=7)

        # At least one of the calls must have used the user-supplied timeout.
        used_timeouts = {t for _, _, t in captured}
        self.assertIn(
            7, used_timeouts,
            f"timeout=7 never reached any HTTP call; got {used_timeouts}",
        )

    def test_cli_main_threads_args_timeout_into_get_weather(self):
        """main() must pass args.timeout to get_weather (not just parse it)."""
        with mock.patch.object(weather_lib, "get_weather") as mock_get:
            mock_get.return_value = {"location": "北京", "province": "北京",
                                      "publish_time": "t", "weather": "晴",
                                      "temperature": "5", "feels_like": "2",
                                      "humidity": "45", "rain_mm": "0",
                                      "comfort_index": "凉",
                                      "wind": {"direct": "东北风", "degree": "45",
                                               "speed_ms": "3", "power": "2级"},
                                      "sunrise": "07:30", "sunset": "17:15",
                                      "alert": None, "forecast": [],
                                      "climate": [], "radar_url": None}
            with mock.patch.object(sys, "argv", ["query.py", "北京", "--timeout", "11"]):
                weather_lib.main()
        self.assertEqual(mock_get.call_args.kwargs.get("timeout"), 11,
                         f"expected timeout=11, got {mock_get.call_args}")


# ====================================================================
# Bug B: malformed NMC data raises uncaught KeyError instead of DataError
# ====================================================================

class TestMalformedDataRaisesDataError(_IsolatedCache):
    """Bug B: any KeyError inside _normalize must surface as DataError (exit 3)."""

    def test_missing_real_block_raises_data_error(self):
        responses = {
            "/rest/province/all": PROVINCES,
            "/rest/province/101010100": BEIJING_CITIES,
            "/rest/province/101020100": SHANGHAI_CITIES,
            "/rest/weather": {"data": {"predict": {"detail": []}}},
        }
        with mock.patch("urllib.request.urlopen",
                        side_effect=_make_route(responses)):
            with self.assertRaises(weather_lib.DataError):
                weather_lib.get_weather("北京", force=True)

    def test_missing_predict_block_raises_data_error(self):
        responses = {
            "/rest/province/all": PROVINCES,
            "/rest/province/101010100": BEIJING_CITIES,
            "/rest/province/101020100": SHANGHAI_CITIES,
            "/rest/weather": {"data": {"real": _ok_weather_payload()["data"]["real"]}},
        }
        with mock.patch("urllib.request.urlopen",
                        side_effect=_make_route(responses)):
            with self.assertRaises(weather_lib.DataError):
                weather_lib.get_weather("北京", force=True)

    def test_missing_day_temperature_raises_data_error(self):
        bad = _ok_weather_payload()
        # Drop a nested field _normalize_day reads
        del bad["data"]["predict"]["detail"][0]["day"]["weather"]["temperature"]
        responses = {
            "/rest/province/all": PROVINCES,
            "/rest/province/101010100": BEIJING_CITIES,
            "/rest/province/101020100": SHANGHAI_CITIES,
            "/rest/weather": bad,
        }
        with mock.patch("urllib.request.urlopen",
                        side_effect=_make_route(responses)):
            with self.assertRaises(weather_lib.DataError):
                weather_lib.get_weather("北京", force=True)


# ====================================================================
# Bug C: _format_human has I/O side effects + drops section on --date miss
# ====================================================================

class TestFormatterIsPure(unittest.TestCase):
    """Bug C: _format_human must be pure (return str only) and always emit a
    forecast section header so output structure is stable."""

    def _make_weather(self):
        return {
            "location": "北京", "province": "北京",
            "publish_time": "2024-01-15 14:00",
            "weather": "晴", "temperature": "5", "feels_like": "2",
            "humidity": "45", "rain_mm": "0", "comfort_index": "凉",
            "wind": {"direct": "东北风", "degree": "45",
                     "speed_ms": "3", "power": "2级"},
            "sunrise": "2024-01-15 07:30", "sunset": "2024-01-15 17:15",
            "alert": None,
            "forecast": [{"date": "2024-01-15",
                          "day": {"weather": "晴", "temperature": "8",
                                  "wind": "北风 2级"},
                          "night": {"weather": "多云", "temperature": "-2",
                                    "wind": "北风 1级"},
                          "precipitation_mm": "0"}],
            "climate": [{"month": "1", "max_temp": "3",
                         "min_temp": "-7", "precip": "3"}],
            "radar_url": "http://www.nmc.cn/radar/beijing.png",
            "_source": "NMC 中央气象台", "_schema_version": "3.0",
        }

    def test_format_human_does_not_write_to_stderr(self):
        args = mock.Mock(date="2099-01-01", days=None, climate=False)
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            weather_lib._format_human(self._make_weather(), args)
        finally:
            sys.stderr = old
        self.assertEqual(buf.getvalue(), "",
                         f"formatter wrote to stderr: {buf.getvalue()!r}")

    def test_format_human_emits_header_even_when_date_misses(self):
        args = mock.Mock(date="2099-01-01", days=None, climate=False)
        out = weather_lib._format_human(self._make_weather(), args)
        self.assertIn("预报", out,
                      "forecast section header must always be present")
        self.assertIn("2099-01-01", out,
                      "missed-date line must echo the requested date")


# ====================================================================
# Bug D: per-province NetworkError silently swallowed → no diagnostic
# ====================================================================

class TestProvinceFailureIsVisible(_IsolatedCache):
    """Bug D: when one province fails to load cities, the failure must reach
    stderr so the user can tell why their query returned a wrong/missing match."""

    def test_failure_logged_to_stderr(self):
        def route(req, **kwargs):
            url = req.full_url
            if url.endswith("/rest/province/all"):
                return _FakeResp(json.dumps(PROVINCES).encode("utf-8"))
            if "101020100" in url:  # Shanghai times out
                raise URLError("simulated timeout")
            if "101010100" in url:
                return _FakeResp(json.dumps(BEIJING_CITIES).encode("utf-8"))
            raise AssertionError(f"unexpected URL: {url}")

        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            with mock.patch("urllib.request.urlopen", side_effect=route):
                stationid, city, province = weather_lib.resolve_stationid("北京")
        finally:
            sys.stderr = old

        self.assertEqual(city, "北京")
        logged = buf.getvalue()
        self.assertIn("101020100", logged,
                      f"Shanghai failure must be logged, got: {logged!r}")


# ====================================================================
# Bug E: --date '2024-1-5' is silently ignored (only '2024-01-05' matches)
# ====================================================================

class TestDateInputIsCanonicalized(unittest.TestCase):
    """Bug E: --date must accept single-digit month/day and normalize to zero-padded."""

    def test_short_date_canonicalized_by_main(self):
        """Passing '2024-1-5' should be treated as '2024-01-05' (lookup match)."""
        weather = {
            "location": "上海", "province": "上海",
            "publish_time": "t", "weather": "晴", "temperature": "5",
            "feels_like": "2", "humidity": "45", "rain_mm": "0",
            "comfort_index": "凉",
            "wind": {"direct": "东", "degree": "90", "speed_ms": "2", "power": "1级"},
            "sunrise": "07:30", "sunset": "17:15", "alert": None,
            "forecast": [{"date": "2024-01-05",
                          "day": {"weather": "晴", "temperature": "8",
                                  "wind": "东 1级"},
                          "night": {"weather": "晴", "temperature": "-1",
                                    "wind": "东 1级"},
                          "precipitation_mm": "0"}],
            "climate": [], "radar_url": None,
        }
        with mock.patch.object(weather_lib, "get_weather", return_value=weather):
            with mock.patch.object(sys, "argv",
                                   ["query.py", "上海", "--date", "2024-1-5"]):
                with mock.patch("builtins.print") as mock_print:
                    rc = weather_lib.main()
        self.assertEqual(rc, 0)
        # All printed lines concatenated — at least one should mention 2024-01-05
        all_text = "\n".join(str(c.args[0]) for c in mock_print.call_args_list
                              if c.args)
        self.assertIn("2024-01-05", all_text,
                      f"canonicalized date missing from output: {all_text!r}")

    def test_malformed_date_returns_exit_1(self):
        with mock.patch.object(sys, "argv",
                               ["query.py", "北京", "--date", "not-a-date"]):
            with mock.patch("builtins.print"):
                rc = weather_lib.main()
        self.assertEqual(rc, 1, "malformed --date must yield exit 1")


# ====================================================================
# Bug F: cache write is non-atomic — corrupt file on crash mid-write
# ====================================================================

class TestCacheWriteIsAtomic(_IsolatedCache):
    """Bug F: _cache_save must use write-then-rename so a crash mid-write
    cannot leave a half-written file behind."""

    def test_no_tmp_file_left_behind(self):
        weather_lib._cache_save("test_cat", "atomic", {"a": 1, "b": [2, 3]})
        # After successful save, no .tmp sidecar should remain.
        siblings = list(Path(self._tmpdir, "test_cat").iterdir())
        tmp_files = [p for p in siblings if p.suffix == ".tmp"]
        self.assertEqual(tmp_files, [],
                         f"tmp files leaked: {tmp_files}")

    def test_uses_os_replace_not_direct_write(self):
        """Implementation must go through tmp + os.replace, not direct write."""
        import inspect
        src = inspect.getsource(weather_lib._cache_save)
        self.assertIn("os.replace", src,
                      "_cache_save must use os.replace for atomicity")
        self.assertIn(".tmp", src,
                      "_cache_save must write to a .tmp sidecar first")

    def test_cache_load_round_trip(self):
        """Sanity: after atomic write, load returns identical data."""
        payload = {"x": "你好", "list": [1, 2, 3]}
        weather_lib._cache_save("test_cat", "roundtrip", payload)
        loaded = weather_lib._cache_load("test_cat", "roundtrip", 999)
        self.assertEqual(loaded, payload)


# ====================================================================
# Regression: happy-path tests so the fixes don't break the normal flow
# ====================================================================

class TestHappyPath(_IsolatedCache):
    """A few green-path tests to make sure the fixes don't regress."""

    def test_resolve_stationid_exact_match(self):
        responses = {
            "/rest/province/all": PROVINCES,
            "/rest/province/101010100": BEIJING_CITIES,
            "/rest/province/101020100": SHANGHAI_CITIES,
        }
        with mock.patch("urllib.request.urlopen",
                        side_effect=_make_route(responses)):
            sid, city, province = weather_lib.resolve_stationid("北京")
        self.assertEqual(city, "北京")
        self.assertEqual(province, "北京")
        self.assertEqual(sid, "101010100")

    def test_resolve_stationid_no_match_raises_input_error(self):
        responses = {
            "/rest/province/all": PROVINCES,
            "/rest/province/101010100": BEIJING_CITIES,
            "/rest/province/101020100": SHANGHAI_CITIES,
        }
        with mock.patch("urllib.request.urlopen",
                        side_effect=_make_route(responses)):
            with self.assertRaises(weather_lib.InputError):
                weather_lib.resolve_stationid("亚特兰蒂斯")

    def test_get_weather_normalizes_real_block(self):
        responses = {
            "/rest/province/all": PROVINCES,
            "/rest/province/101010100": BEIJING_CITIES,
            "/rest/province/101020100": SHANGHAI_CITIES,
            "/rest/weather": _ok_weather_payload(),
        }
        with mock.patch("urllib.request.urlopen",
                        side_effect=_make_route(responses)):
            w = weather_lib.get_weather("北京", force=True)
        self.assertEqual(w["location"], "北京")
        self.assertEqual(w["weather"], "晴")
        self.assertEqual(w["temperature"], "5")
        self.assertEqual(w["forecast"][0]["date"], "2024-01-15")
        # Sentinel '' → None
        self.assertIsNone(w["alert"])


if __name__ == "__main__":
    unittest.main()
