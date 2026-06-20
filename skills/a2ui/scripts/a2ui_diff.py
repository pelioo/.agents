#!/usr/bin/env python3
"""
a2ui_diff.py — Compute minimal A2UI update from two data snapshots.

Given the previous dataModel.data and the current dataModel.data, emit the
smallest possible updateDataModel payload that transitions the UI.

This is the highest-leverage tool for token cost: typical "data refresh"
scenarios go from ~200 tokens (full updateComponents) to ~30 tokens
(diff-only updateDataModel), a ~85% reduction.

Usage:
    # Save current data snapshot (for next diff)
    python a2ui_render.py update --progress 0.52 --metric "粉丝数=5172" -o snapshot.json
    # ... later ...
    python a2ui_render.py update --progress 0.67 --metric "粉丝数=5891" -o new.json
    python a2ui_diff.py --prev snapshot.json --next new.json -o diff.json

    # Or read existing A2UI messages files and diff their updateDataModel data
    python a2ui_diff.py --from-msgs prev_msgs.json --from-msgs next_msgs.json -o diff.json

    # With stats
    python a2ui_diff.py --prev a.json --next b.json --stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a2ui_core import (
    SURFACE_ID,
    diff_data,
    payload_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_data_from_msgs(messages: list[dict]) -> dict | None:
    """
    Extract the latest dataModel.data dict from a list of A2UI messages.

    Looks for the LAST updateDataModel message and returns its data.
    Returns None if no updateDataModel found.
    """
    latest = None
    for m in messages:
        if isinstance(m, dict) and "updateDataModel" in m:
            latest = m["updateDataModel"].get("data")
    return latest


def load_data_file(path: Path) -> dict | None:
    """
    Load data from a file. Smart enough to handle:
    - Pure data dict: {"foo": "bar"}
    - A2UI messages: {"messages": [...]}
    - Plain text snapshot: just the data
    """
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    obj = json.loads(content)
    if isinstance(obj, dict):
        if "messages" in obj and isinstance(obj["messages"], list):
            return extract_data_from_msgs(obj["messages"])
        if "data" in obj and isinstance(obj["data"], dict):
            return obj["data"]
        # Heuristic: pure data dict
        return obj
    return None


def build_diff_payload(prev: dict | None, next_: dict, surface_id: str = SURFACE_ID) -> dict | None:
    """
    Build the minimal A2UI messages payload for the diff.

    Returns None if no changes (empty update is wasteful).
    """
    data = diff_data(prev, next_)
    if data is None:
        return None
    return {"messages": [{"updateDataModel": {"surfaceId": surface_id, "data": data}}]}


# ---------------------------------------------------------------------------
# Subcommand
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="a2ui_diff",
        description="Compute minimal A2UI update from two data snapshots.",
    )
    p.add_argument("--prev", help="Previous data or messages file (or '-' for stdin)")
    p.add_argument("--next", help="Next data or messages file (or '-' for stdin)")
    p.add_argument("--surface", default=SURFACE_ID, help="Surface ID (default: main)")
    p.add_argument("--output", "-o", help="Output file (default: stdout)")
    p.add_argument("--stats", action="store_true", help="Print payload stats to stderr")
    p.add_argument("--quiet-no-change", action="store_true",
                   help="Exit silently (code 0) if no changes detected")
    return p


def _load_input(path_arg: str) -> dict | None:
    """Load a data snapshot from a file path or stdin (`-`)."""
    if path_arg == "-":
        return json.loads(sys.stdin.read())
    return load_data_file(Path(path_arg))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.prev or not args.next:
        print("error: --prev and --next are required", file=sys.stderr)
        return 2

    # Reject both `-` — second stdin read returns empty string and crashes
    # JSONDecoder. Document the constraint instead of crashing.
    if args.prev == "-" and args.next == "-":
        print("error: only one of --prev/--next may be '-' (stdin)", file=sys.stderr)
        return 2

    try:
        prev = _load_input(args.prev)
        next_ = _load_input(args.next)
    except FileNotFoundError as e:
        print(f"error: file not found: {e.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in input: {e}", file=sys.stderr)
        return 2

    if next_ is None:
        print("error: could not extract data from --next", file=sys.stderr)
        return 2

    payload = build_diff_payload(prev, next_, surface_id=args.surface)

    if payload is None:
        if not args.quiet_no_change:
            print("[a2ui_diff] no changes", file=sys.stderr)
        return 0

    if args.stats:
        stats = payload_stats(payload)
        # Also report what % was saved vs full
        full_stats = payload_stats({"messages": [{"updateDataModel": {"surfaceId": args.surface, "data": next_}}]})
        saved_pct = 100 * (1 - stats["tokens_est"] / full_stats["tokens_est"]) if full_stats["tokens_est"] else 0
        print(f"[stats] diff={stats['tokens_est']} tokens, full={full_stats['tokens_est']} tokens, saved={saved_pct:.1f}%",
              file=sys.stderr)

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())