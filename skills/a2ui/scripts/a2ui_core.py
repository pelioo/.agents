"""
A2UI JSON generation core.

This module is the single source of truth for mapping business data to A2UI JSON.
Both `a2ui_render.py` (full render) and `a2ui_diff.py` (incremental diff) use it.

Design goals:
1. Agent never needs to know A2UI JSON structure — pass business data, get JSON.
2. Minimize output size — choose updateDataModel path when possible.
3. Minimize token cost — semantic IDs, no redundant fields.
4. Stable across calls — same data input → same JSON output (idempotent for diff).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SURFACE_ID = "main"
CATALOG_ID = "cteno/v1"

# Sentinel used by diff helpers to indicate "no change" in a subtree.
_UNCHANGED = object()


# ---------------------------------------------------------------------------
# Path & ID utilities
# ---------------------------------------------------------------------------

def semantic_id(prefix: str, key: str) -> str:
    """
    Generate a stable, semantic component ID.

    Examples:
        semantic_id("metric", "粉丝数") -> "metric-粉丝数"
        semantic_id("metric", "cpu_usage") -> "metric-cpu-usage"
        semantic_id("metric", "粉丝数-动态") -> "metric-粉丝数-动态"

    Keeps ASCII letters/digits + all Unicode letters (CJK, Cyrillic, etc).
    Separators (whitespace, punctuation, underscore) become hyphens.
    The ID is deterministic so the same data field always maps to the same
    component, enabling incremental updates to replace in-place.
    """
    if not key:
        return prefix
    # [^\W_]+ = Unicode letters/digits, excluding underscore (treated as separator).
    # re.UNICODE is the default in Python 3 for str patterns, set explicitly for clarity.
    parts = re.findall(r"[^\W_]+", key, flags=re.UNICODE)
    slug = "-".join(parts).lower()
    return f"{prefix}-{slug}" if slug else prefix


def data_path(*parts: str) -> str:
    """
    Build a `${dataModel.path}` reference string.

    Example:
        data_path("cpu", "usage") -> "${cpu.usage}"
    """
    return "${" + ".".join(parts) + "}"


# ---------------------------------------------------------------------------
# Render modes
# ---------------------------------------------------------------------------

def render_initial(
    *,
    title: str,
    metrics: dict[str, Any] | None = None,
    progress: float | None = None,
    progress_label: str = "总进度",
    status: str = "active",
    status_text: str = "运行中",
    activity: list[tuple[str, str]] | None = None,
    surface_id: str = SURFACE_ID,
) -> dict[str, Any]:
    """
    Generate the initial A2UI JSON for a dashboard surface.

    Args:
        title: Card title (e.g. "抖音涨粉看板").
        metrics: Dict of label -> value (e.g. {"粉丝数": 5172, "目标": 10000}).
                 Will be rendered via MetricsGrid for auto layout.
        progress: Float 0.0-1.0. None to omit Progress component.
        progress_label: Label text for the Progress bar.
        status: StatusIndicator status ("active"/"idle"/"error").
        status_text: StatusIndicator text.
        activity: List of (timestamp, text) tuples for ActivityFeed.
        surface_id: Surface identifier (default "main").

    Returns:
        A dict with "messages" key ready to be serialized as A2UI JSON.

    Optimization:
        Uses updateDataModel for the actual values, so subsequent updates
        only need to send data (small payload).
    """
    metrics = metrics or {}
    activity = activity or []
    messages: list[dict[str, Any]] = []

    # 1. createSurface
    messages.append({"createSurface": {"surfaceId": surface_id, "catalogId": CATALOG_ID}})

    # 2. Build component tree
    components: list[dict[str, Any]] = []

    # Root Container
    children_ids: list[str] = []
    components.append({"id": "root", "component": "Container", "children": []})

    # Status indicator (optional but common)
    status_id = semantic_id("status", "indicator")
    children_ids.append(status_id)
    components.append({
        "id": status_id,
        "component": "StatusIndicator",
        "status": data_path("status", "value"),
        "text": data_path("status", "text"),
    })

    # Card
    card_id = semantic_id("card", title)
    children_ids.append(card_id)
    card_children: list[str] = []
    components.append({
        "id": card_id,
        "component": "Card",
        "title": data_path("card", "title"),
        "children": card_children,
    })

    # Progress (optional)
    if progress is not None:
        prog_id = semantic_id("progress", progress_label)
        card_children.append(prog_id)
        components.append({
            "id": prog_id,
            "component": "Progress",
            "value": data_path("progress", "value"),
            "label": data_path("progress", "label"),
        })

    # MetricsGrid (preferred for 2+ metrics)
    if metrics:
        metrics_id = semantic_id("metrics", "grid")
        card_children.append(metrics_id)
        components.append({
            "id": metrics_id,
            "component": "MetricsGrid",
            "metrics": "{}",  # placeholder; real structure built via dataModel
        })

    # ActivityFeed (optional)
    if activity:
        feed_id = semantic_id("feed", "activity")
        card_children.append(feed_id)
        components.append({
            "id": feed_id,
            "component": "ActivityFeed",
            "items": [],  # placeholder; populated via dataModel
        })

    # Wire root children
    components[0]["children"] = children_ids

    messages.append({"updateComponents": {"surfaceId": surface_id, "components": components}})

    # 3. Build initial dataModel
    data: dict[str, Any] = {
        "card": {"title": title},
        "status": {"value": status, "text": status_text},
    }
    if progress is not None:
        data["progress"] = {"value": float(progress), "label": progress_label}
    if metrics:
        # MetricsGrid expects a flat record (label -> value)
        data["metrics"] = {str(k): str(v) for k, v in metrics.items()}
    if activity:
        data["activity"] = [
            {"text": text, "timestamp": ts} for ts, text in activity
        ]
    messages.append({"updateDataModel": {"surfaceId": surface_id, "data": data}})

    return {"messages": messages}


def render_incremental(
    *,
    metrics: dict[str, Any] | None = None,
    progress: float | None = None,
    progress_label: str | None = None,
    status: str | None = None,
    status_text: str | None = None,
    surface_id: str = SURFACE_ID,
) -> dict[str, Any]:
    """
    Generate a minimal incremental update (updateDataModel only).

    Only includes fields that are explicitly provided (non-None).
    Use this for high-frequency refreshes where component structure doesn't change.

    Raises:
        ValueError: if `progress_label` is provided without `progress` (otherwise
            the label would be silently dropped, leading to confusing no-op updates).
    """
    if progress_label is not None and progress is None:
        raise ValueError(
            "progress_label requires progress value; "
            "otherwise the label would be silently dropped."
        )
    data: dict[str, Any] = {}
    if status is not None or status_text is not None:
        data["status"] = {}
        if status is not None:
            data["status"]["value"] = status
        if status_text is not None:
            data["status"]["text"] = status_text
    if progress is not None:
        data["progress"] = {"value": float(progress)}
        if progress_label is not None:
            data["progress"]["label"] = progress_label
    if metrics:
        data["metrics"] = {str(k): str(v) for k, v in metrics.items()}

    return {"messages": [{"updateDataModel": {"surfaceId": surface_id, "data": data}}]}


# ---------------------------------------------------------------------------
# Diff: compute minimal update between two data snapshots
# ---------------------------------------------------------------------------

def diff_data(
    prev: dict[str, Any] | None,
    next_: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Compute minimal data update from prev to next_.

    Returns a dict containing only changed fields, or None if no changes.

    Algorithm: recursive comparison with two special cases:
    1. Flat scalar records (MetricsGrid heuristic): treat as dict-of-scalars,
       diff each scalar independently.
    2. Lists (activity feeds): full replace on any change.

    Args:
        prev: Previous dataModel.data dict (or None for first call).
        next_: Current dataModel.data dict.

    Returns:
        Minimal data dict with only changed fields, or None if identical.
    """
    if prev is None:
        return next_
    if next_ is None:
        return None

    result = _diff_recursive(prev, next_)
    if result is _UNCHANGED:
        return None
    return result


def _diff_recursive(prev: Any, next_: Any) -> Any:
    """
    Recursive diff. Returns the minimal subtree that changed, or a sentinel
    `_UNCHANGED` if identical.

    Semantics:
    - Key missing in next_ but present in prev → UNCHANGED (don't delete).
      (UpdateDataModel merges; missing keys stay. We never explicitly delete.)
    - Key missing in prev but present in next_ → INCLUDE (new field).
    - Both present and different → recurse (dict) or replace (scalar/list).
    - MetricsGrid: a dict whose all values are scalars is treated as a flat
      record (no nested `.values` wrapper in the wire format).
    """
    if prev == next_:
        return _UNCHANGED

    # next_ is dict but prev isn't → include next_ entirely
    if isinstance(next_, dict) and not isinstance(prev, dict):
        return next_

    # If both are dicts, recurse field by field
    if isinstance(prev, dict) and isinstance(next_, dict):
        # MetricsGrid heuristic: a dict with all scalar values (and no
        # nested __type marker / values wrapper). Treat it as a flat record.
        if _is_flat_scalar_record(prev) and _is_flat_scalar_record(next_):
            result: dict[str, Any] = {}
            for k in next_.keys():
                sub = _diff_recursive(prev.get(k), next_[k])
                if sub is not _UNCHANGED:
                    result[k] = sub
            if not result:
                return _UNCHANGED
            return result

        # General nested dict
        result = {}
        for k in next_.keys():
            sub = _diff_recursive(prev.get(k), next_[k])
            if sub is not _UNCHANGED:
                result[k] = sub
        if not result:
            return _UNCHANGED
        return result

    # For lists or scalars: any difference = full replace
    if prev != next_:
        return next_
    return _UNCHANGED


def _is_flat_scalar_record(d: Any) -> bool:
    """
    True if `d` looks like a MetricsGrid record: all values are scalar
    (str/number/bool/None) and there are no nested dict/list children.
    """
    if not isinstance(d, dict) or not d:
        return False
    for v in d.values():
        if isinstance(v, (dict, list)):
            return False
    return True


# ---------------------------------------------------------------------------
# Token cost estimation (for benchmarking)
# ---------------------------------------------------------------------------

def estimate_tokens(payload: dict[str, Any] | str) -> int:
    """
    Rough token estimate for a JSON payload.

    Uses a simple heuristic: ~4 chars per token (GPT-style average).
    Not exact but good enough for relative comparisons.
    """
    if isinstance(payload, dict):
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = payload
    return max(1, len(text) // 4)


def payload_stats(payload: dict[str, Any]) -> dict[str, int]:
    """
    Compute size statistics for a payload.
    """
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "bytes": len(text.encode("utf-8")),
        "chars": len(text),
        "tokens_est": estimate_tokens(text),
    }


# ---------------------------------------------------------------------------
# Stable hashing (for tests/diff verification)
# ---------------------------------------------------------------------------

def stable_hash(obj: Any) -> str:
    """Deterministic hash of a JSON-serializable object."""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]