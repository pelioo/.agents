"""
Tests for a2ui_diff.py incremental diff logic.

Run: python -m unittest skills/a2ui/tests/test_diff.py
"""

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from a2ui_core import diff_data, _diff_recursive, _is_flat_scalar_record, _UNCHANGED  # noqa: E402


class TestDiffNoneAndEmpty(unittest.TestCase):

    def test_no_prev_returns_next(self):
        """If prev is None, return next_ entirely."""
        next_ = {"foo": "bar"}
        self.assertEqual(diff_data(None, next_), next_)

    def test_identical_returns_none(self):
        """Identical data should yield None (no update needed)."""
        d = {"a": 1, "b": {"c": 2}}
        self.assertIsNone(diff_data(d, d))

    def test_empty_dicts(self):
        self.assertIsNone(diff_data({}, {}))


class TestDiffFlatFields(unittest.TestCase):

    def test_single_field_change(self):
        prev = {"a": 1, "b": 2, "c": 3}
        next_ = {"a": 1, "b": 99, "c": 3}
        result = diff_data(prev, next_)
        self.assertEqual(result, {"b": 99})

    def test_new_field_added(self):
        prev = {"a": 1}
        next_ = {"a": 1, "b": 2}
        result = diff_data(prev, next_)
        self.assertEqual(result, {"b": 2})

    def test_field_removed_is_kept(self):
        """We don't emit deletes (updateDataModel merges)."""
        prev = {"a": 1, "b": 2}
        next_ = {"a": 1}
        result = diff_data(prev, next_)
        self.assertIsNone(result, "Removing a field should not produce a diff")


class TestDiffNested(unittest.TestCase):

    def test_nested_field_change(self):
        prev = {"outer": {"inner": "old", "sibling": "same"}}
        next_ = {"outer": {"inner": "new", "sibling": "same"}}
        result = diff_data(prev, next_)
        self.assertEqual(result, {"outer": {"inner": "new"}})

    def test_nested_field_missing_in_next_kept(self):
        """Missing subkey in next_ should not produce a null overwrite."""
        prev = {"outer": {"inner": "x", "label": "y"}}
        next_ = {"outer": {"inner": "x"}}
        result = diff_data(prev, next_)
        self.assertIsNone(result)


class TestDiffMetricsGrid(unittest.TestCase):

    def test_one_metric_of_many_changes(self):
        prev = {"metrics": {"a": "1", "b": "2", "c": "3", "d": "4"}}
        next_ = {"metrics": {"a": "1", "b": "CHANGED", "c": "3", "d": "4"}}
        result = diff_data(prev, next_)
        self.assertEqual(result, {"metrics": {"b": "CHANGED"}})

    def test_chinese_metric_keys(self):
        prev = {"metrics": {"粉丝数": "5172", "目标": "10000"}}
        next_ = {"metrics": {"粉丝数": "5891", "目标": "10000"}}
        result = diff_data(prev, next_)
        self.assertEqual(result, {"metrics": {"粉丝数": "5891"}})


class TestDiffLists(unittest.TestCase):

    def test_list_change_full_replace(self):
        prev = {"activity": [{"text": "A", "ts": "1"}]}
        next_ = {"activity": [{"text": "B", "ts": "2"}]}
        result = diff_data(prev, next_)
        self.assertEqual(result, {"activity": [{"text": "B", "ts": "2"}]})


class TestFlatRecordDetection(unittest.TestCase):

    def test_flat_scalar_record(self):
        self.assertTrue(_is_flat_scalar_record({"a": "1", "b": 2}))
        self.assertTrue(_is_flat_scalar_record({"粉丝数": "5172"}))

    def test_not_flat_with_nested(self):
        self.assertFalse(_is_flat_scalar_record({"a": {"b": 1}}))
        self.assertFalse(_is_flat_scalar_record({"a": [1, 2]}))

    def test_not_flat_when_empty(self):
        self.assertFalse(_is_flat_scalar_record({}))


class TestRecursion(unittest.TestCase):

    def test_unchanged_sentinel(self):
        result = _diff_recursive({"a": 1}, {"a": 1})
        self.assertIs(result, _UNCHANGED)

    def test_scalar_diff(self):
        self.assertEqual(_diff_recursive(1, 2), 2)
        self.assertEqual(_diff_recursive("a", "b"), "b")


if __name__ == "__main__":
    unittest.main(verbosity=2)