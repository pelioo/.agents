"""
Unit tests for a2ui_render.py and a2ui_core.py render functions.

Run: python -m unittest skills/a2ui/tests/test_render.py
"""

import json
import sys
import unittest
from pathlib import Path

# Allow tests to import scripts/
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from a2ui_core import render_initial, render_incremental, payload_stats, semantic_id  # noqa: E402


class TestRenderInitial(unittest.TestCase):

    def test_minimal_title_only(self):
        """Title-only should produce valid structure with just Card + Status."""
        result = render_initial(title="Test")
        msgs = result["messages"]
        self.assertEqual(len(msgs), 3, "Expected createSurface + updateComponents + updateDataModel")
        self.assertIn("createSurface", msgs[0])
        self.assertIn("updateComponents", msgs[1])
        self.assertIn("updateDataModel", msgs[2])
        # Must have Card + StatusIndicator
        comp_types = [c["component"] for c in msgs[1]["updateComponents"]["components"]]
        self.assertIn("Card", comp_types)
        self.assertIn("StatusIndicator", comp_types)
        self.assertIn("Container", comp_types)

    def test_with_metrics(self):
        """Metrics should produce MetricsGrid component."""
        result = render_initial(title="D", metrics={"A": 1, "B": 2})
        comps = result["messages"][1]["updateComponents"]["components"]
        types = [c["component"] for c in comps]
        self.assertIn("MetricsGrid", types)
        # Data should contain flat metric record
        data = result["messages"][2]["updateDataModel"]["data"]
        self.assertIn("metrics", data)
        self.assertEqual(data["metrics"], {"A": "1", "B": "2"})

    def test_with_progress(self):
        """Progress value should be in data and Progress component present."""
        result = render_initial(title="D", progress=0.42)
        comps = result["messages"][1]["updateComponents"]["components"]
        ids = [c["id"] for c in comps]
        self.assertTrue(any("progress" in i for i in ids))
        data = result["messages"][2]["updateDataModel"]["data"]
        self.assertEqual(data["progress"]["value"], 0.42)

    def test_with_activity(self):
        """Activity should produce ActivityFeed with items."""
        result = render_initial(title="D", activity=[("10:00", "A"), ("11:00", "B")])
        comps = result["messages"][1]["updateComponents"]["components"]
        types = [c["component"] for c in comps]
        self.assertIn("ActivityFeed", types)
        data = result["messages"][2]["updateDataModel"]["data"]
        self.assertEqual(len(data["activity"]), 2)
        self.assertEqual(data["activity"][0]["timestamp"], "10:00")

    def test_chinese_keys(self):
        """Chinese metric labels must round-trip through UTF-8."""
        result = render_initial(title="测试", metrics={"粉丝数": "5172"})
        data = result["messages"][2]["updateDataModel"]["data"]
        self.assertIn("粉丝数", data["metrics"])

    def test_status_default(self):
        """Status should default to active/运行中."""
        result = render_initial(title="D")
        data = result["messages"][2]["updateDataModel"]["data"]
        self.assertEqual(data["status"]["value"], "active")
        self.assertEqual(data["status"]["text"], "运行中")


class TestRenderIncremental(unittest.TestCase):

    def test_minimal_empty(self):
        """No args should still produce valid structure."""
        result = render_incremental()
        msgs = result["messages"]
        self.assertEqual(len(msgs), 1)
        self.assertIn("updateDataModel", msgs[0])
        # No fields provided → empty data
        self.assertEqual(msgs[0]["updateDataModel"]["data"], {})

    def test_progress_only(self):
        result = render_incremental(progress=0.5)
        data = result["messages"][0]["updateDataModel"]["data"]
        self.assertIn("progress", data)
        self.assertEqual(data["progress"]["value"], 0.5)
        # Label should NOT be in data when not provided
        self.assertNotIn("label", data["progress"])

    def test_metrics_only(self):
        result = render_incremental(metrics={"A": "1"})
        data = result["messages"][0]["updateDataModel"]["data"]
        self.assertEqual(data["metrics"], {"A": "1"})


class TestPayloadStats(unittest.TestCase):

    def test_stats_keys(self):
        result = render_initial(title="D", metrics={"A": 1})
        stats = payload_stats(result)
        self.assertIn("bytes", stats)
        self.assertIn("chars", stats)
        self.assertIn("tokens_est", stats)
        self.assertGreater(stats["bytes"], 0)
        self.assertGreater(stats["tokens_est"], 0)


class TestSemanticID(unittest.TestCase):
    """Regression tests for HIGH bug: semantic_id() must keep CJK chars."""

    def test_chinese_preserved(self):
        self.assertEqual(semantic_id("metric", "粉丝数"), "metric-粉丝数")
        self.assertEqual(semantic_id("metric", "粉丝数-动态"), "metric-粉丝数-动态")

    def test_ascii_underscore_as_separator(self):
        """Underscore still acts as separator (matches original docstring)."""
        self.assertEqual(semantic_id("metric", "cpu_usage"), "metric-cpu-usage")

    def test_empty_or_punctuation_only_returns_just_prefix(self):
        self.assertEqual(semantic_id("metric", ""), "metric")
        self.assertEqual(semantic_id("metric", "---"), "metric")
        self.assertEqual(semantic_id("metric", "___"), "metric")

    def test_two_chinese_titles_distinct_card_ids(self):
        """Regression: two Chinese titles must produce distinct Card IDs in render_initial."""
        a = render_initial(title="抖音涨粉看板")
        b = render_initial(title="小红书涨粉看板")
        cards_a = [c for c in a["messages"][1]["updateComponents"]["components"] if c["component"] == "Card"]
        cards_b = [c for c in b["messages"][1]["updateComponents"]["components"] if c["component"] == "Card"]
        self.assertEqual(len(cards_a), 1)
        self.assertEqual(len(cards_b), 1)
        self.assertNotEqual(cards_a[0]["id"], cards_b[0]["id"],
                            "Different Chinese titles collided on the same Card ID")
        self.assertIn("抖音", cards_a[0]["id"])
        self.assertIn("小红书", cards_b[0]["id"])


class TestRenderIncrementalValidation(unittest.TestCase):
    """Regression: progress_label without progress must error loudly, not silently drop."""

    def test_progress_label_without_progress_raises(self):
        with self.assertRaises(ValueError) as ctx:
            render_incremental(progress_label="新进度")
        self.assertIn("progress_label", str(ctx.exception))


class TestCliExitCodes(unittest.TestCase):
    """
    Regression: CLI must surface validation errors as friendly single-line
    stderr messages with exit code 2 (not Python tracebacks with exit 1),
    so Agent callers can react programmatically.
    """

    def _run_cli(self, *args: str) -> tuple[int, str, str]:
        """Run a2ui_render.main() with the given argv, capture stdout/stderr.

        argparse's parser.error() calls sys.exit(2), so we catch SystemExit
        and report its code as the return code. The module is reloaded here
        to ensure tests run against the on-disk source (unittest discovery
        can otherwise hold a cached version across test files).
        """
        import io
        import importlib
        mod = importlib.import_module("a2ui_render")
        importlib.reload(mod)
        out, err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        rc = 0
        try:
            rc = mod.main(list(args))
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        return rc, out.getvalue(), err.getvalue()

    def test_initial_without_title_errors_with_exit_2(self):
        """Regression: missing --title on `initial` must NOT silently emit
        `"title": null`. Must exit 2 with a friendly message."""
        rc, _out, err = self._run_cli("initial")
        self.assertEqual(rc, 2)
        self.assertIn("--title", err)
        self.assertNotIn("Traceback", err, "Should not leak Python traceback")

    def test_progress_out_of_range_errors_with_exit_2(self):
        rc, _out, err = self._run_cli("initial", "--title", "T", "--progress", "1.5")
        self.assertEqual(rc, 2)
        self.assertIn("error:", err)
        self.assertIn("out of range", err)
        self.assertNotIn("Traceback", err)

    def test_invalid_metric_format_errors_with_exit_2(self):
        rc, _out, err = self._run_cli("initial", "--title", "T", "--metric", "noequals")
        self.assertEqual(rc, 2)
        self.assertIn("error:", err)
        self.assertIn("noequals", err)
        self.assertNotIn("Traceback", err)


class TestDiffCliExitCodes(unittest.TestCase):
    """
    Regression: a2ui_diff must surface FileNotFoundError / JSONDecodeError
    as friendly stderr messages with exit 2, and reject two-stdin inputs.
    """

    def _run_cli(self, *args: str) -> tuple[int, str, str]:
        import io
        import importlib
        mod = importlib.import_module("a2ui_diff")
        importlib.reload(mod)
        out, err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        rc = 0
        try:
            rc = mod.main(list(args))
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        return rc, out.getvalue(), err.getvalue()

    def test_missing_file_errors_with_exit_2(self):
        rc, _out, err = self._run_cli("--prev", "does_not_exist.json", "--next", "also_missing.json")
        self.assertEqual(rc, 2)
        self.assertIn("error:", err)
        self.assertIn("does_not_exist.json", err)
        self.assertNotIn("Traceback", err)

    def test_two_stdin_dash_inputs_rejected(self):
        """Regression: --prev - --next - would crash on second stdin read."""
        rc, _out, err = self._run_cli("--prev", "-", "--next", "-")
        self.assertEqual(rc, 2)
        self.assertIn("error:", err)
        self.assertIn("stdin", err.lower())
        self.assertNotIn("Traceback", err)

    def test_invalid_json_errors_with_exit_2(self,):
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not valid json {")
            bad_path = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write('{"messages": []}')
            ok_path = f.name
        try:
            rc, _out, err = self._run_cli("--prev", bad_path, "--next", ok_path)
            self.assertEqual(rc, 2)
            self.assertIn("error:", err)
            self.assertIn("JSON", err)
            self.assertNotIn("Traceback", err)
        finally:
            Path(bad_path).unlink(missing_ok=True)
            Path(ok_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)