"""
Benchmark tests: measure token cost savings from a2ui_diff.py.

Goal: prove that the diff path meaningfully reduces token cost vs full updates
across realistic scenarios.

Run: python -m unittest skills/a2ui/tests/test_bench.py
"""

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from a2ui_core import (  # noqa: E402
    render_initial,
    render_incremental,
    diff_data,
    payload_stats,
)


def _payload_size(payload: dict) -> dict:
    return payload_stats(payload)


def _diff_vs_full(prev_data: dict, next_data: dict, surface_id: str = "main") -> tuple[int, int, float]:
    """Return (full_tokens, diff_tokens, saved_pct)."""
    full = {"messages": [{"updateDataModel": {"surfaceId": surface_id, "data": next_data}}]}
    diff_data_dict = diff_data(prev_data, next_data)
    if diff_data_dict is None:
        return _payload_size(full)["tokens_est"], 0, 100.0
    diff = {"messages": [{"updateDataModel": {"surfaceId": surface_id, "data": diff_data_dict}}]}
    full_t = _payload_size(full)["tokens_est"]
    diff_t = _payload_size(diff)["tokens_est"]
    saved = 100 * (1 - diff_t / full_t) if full_t else 0
    return full_t, diff_t, saved


class TestBenchmarkScenarios(unittest.TestCase):

    def test_high_frequency_one_metric(self):
        """Most common scenario: 1 of N metrics changes per tick."""
        initial = render_initial(
            title="Dashboard",
            metrics={f"m{i}": f"v{i}" for i in range(10)},
            progress=0.5,
        )
        prev = initial["messages"][-1]["updateDataModel"]["data"]

        next_data = dict(prev)
        next_data["metrics"] = dict(prev["metrics"])
        next_data["metrics"]["m3"] = "CHANGED"
        next_data["progress"] = {"value": 0.51, "label": "总进度"}

        full_t, diff_t, saved = _diff_vs_full(prev, next_data)
        print(f"\n[bench] 10 metrics, 1 changed: full={full_t}t diff={diff_t}t saved={saved:.1f}%")
        self.assertGreater(saved, 30, f"Expected >30% savings, got {saved:.1f}%")

    def test_progress_only_update(self):
        """Only progress changes — should save a lot."""
        initial = render_initial(
            title="D",
            metrics={"a": "1", "b": "2", "c": "3"},
            progress=0.5,
        )
        prev = initial["messages"][-1]["updateDataModel"]["data"]

        next_data = dict(prev)
        next_data["progress"] = {"value": 0.99, "label": "总进度"}

        full_t, diff_t, saved = _diff_vs_full(prev, next_data)
        print(f"\n[bench] progress only: full={full_t}t diff={diff_t}t saved={saved:.1f}%")
        self.assertGreater(saved, 50, f"Expected >50% savings for progress-only, got {saved:.1f}%")

    def test_no_change_no_diff(self):
        """Identical snapshots produce None diff (no wasted tokens)."""
        d = {"progress": {"value": 0.5}, "metrics": {"a": "1"}}
        full_t, diff_t, saved = _diff_vs_full(d, d)
        self.assertEqual(diff_t, 0)
        self.assertEqual(saved, 100.0)
        print(f"\n[bench] no change: full={full_t}t diff={diff_t}t saved={saved:.1f}%")

    def test_all_changed_worst_case(self):
        """Worst case: everything changes — diff ≈ full."""
        initial = render_initial(
            title="D",
            metrics={"a": "1", "b": "2"},
            progress=0.5,
        )
        prev = initial["messages"][-1]["updateDataModel"]["data"]
        next_data = {
            "card": {"title": "D"},
            "status": {"value": "active", "text": "运行中"},
            "progress": {"value": 0.99, "label": "总进度"},
            "metrics": {"a": "DIFF", "b": "DIFF"},
        }
        full_t, diff_t, saved = _diff_vs_full(prev, next_data)
        print(f"\n[bench] all changed: full={full_t}t diff={diff_t}t saved={saved:.1f}%")
        # Worst case still shouldn't be much larger than full
        self.assertLess(diff_t, full_t * 1.2,
                        f"Diff should not exceed 120% of full when everything changes")


class TestRenderVsManual(unittest.TestCase):

    def test_render_size_reasonable(self):
        """
        a2ui_render output is somewhat larger than a minimal hand-crafted JSON
        because it adds convenience components (StatusIndicator, semantic IDs,
        Container wrapper). The tradeoff: Agent saves time/effort by not
        hand-crafting JSON. Verify size stays within 2x of minimal.
        """
        manual = {
            "messages": [
                {"createSurface": {"surfaceId": "main", "catalogId": "cteno/v1"}},
                {"updateComponents": {"surfaceId": "main", "components": [
                    {"id": "root", "component": "Container", "children": ["c1"]},
                    {"id": "c1", "component": "Card", "title": "T", "children": ["m"]},
                    {"id": "m", "component": "MetricsGrid", "metrics": {"A": "1", "B": "2"}},
                ]}},
                {"updateDataModel": {"surfaceId": "main", "data": {
                    "card": {"title": "T"},
                    "metrics": {"A": "1", "B": "2"},
                }}},
            ]
        }
        auto = render_initial(title="T", metrics={"A": "1", "B": "2"})
        manual_t = _payload_size(manual)["tokens_est"]
        auto_t = _payload_size(auto)["tokens_est"]
        print(f"\n[bench] manual={manual_t}t auto={auto_t}t (ratio={auto_t/manual_t:.2f})")
        # Auto output is allowed to be up to 2x larger for convenience features
        self.assertLess(auto_t, manual_t * 2,
                        f"Auto output too bloated: {auto_t}t vs manual {manual_t}t")


if __name__ == "__main__":
    unittest.main(verbosity=2)