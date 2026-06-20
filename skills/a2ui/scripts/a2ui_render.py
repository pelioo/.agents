#!/usr/bin/env python3
"""
a2ui_render.py — Generate A2UI JSON from business data.

This is the CLI front-end for Agent / shell usage. Pass business data via
flags, get a complete A2UI JSON on stdout or to a file.

Usage:
    # Initial render
    python a2ui_render.py initial \
        --title "抖音涨粉看板" \
        --metric "粉丝数=5172" \
        --metric "目标=10000" \
        --progress 0.52 \
        --activity "10:30|完成竞品分析" \
        --activity "14:15|发布观点视频" \
        --output initial.json

    # Incremental update (much smaller payload)
    python a2ui_render.py update \
        --progress 0.67 \
        --metric "粉丝数=5891" \
        --output update.json

    # Show payload stats
    python a2ui_render.py initial --title "Test" --metric "A=1" --stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from a2ui_core import (
    render_initial,
    render_incremental,
    payload_stats,
)

# Sentinel for argparse defaults: distinguishes "user did not pass --progress-label"
# from "user passed --progress-label='总进度'". Required because the natural default
# "总进度" is also a legitimate user value that we must not strip.
_UNSET = object()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_kv(arg: str, sep: str = "=") -> tuple[str, str]:
    """Parse 'key=value' or 'key|value' style args."""
    if sep not in arg:
        raise ValueError(f"Invalid format '{arg}', expected 'key{sep}value'")
    k, v = arg.split(sep, 1)
    return k.strip(), v.strip()


def parse_metric(arg: str) -> tuple[str, str]:
    """Parse --metric 'label=value' -> (label, value)."""
    return parse_kv(arg, "=")


def parse_activity(arg: str) -> tuple[str, str]:
    """Parse --activity 'time|text' -> (time, text)."""
    return parse_kv(arg, "|")


def parse_progress(arg: str) -> float:
    """Parse --progress '0.52' -> 0.52."""
    try:
        v = float(arg)
    except ValueError as e:
        raise ValueError(f"Invalid progress value '{arg}': must be a number") from e
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"Progress {v} out of range [0.0, 1.0]")
    return v


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_initial(args: argparse.Namespace) -> dict:
    metrics = dict(parse_metric(m) for m in args.metric) if args.metric else None
    activity = [parse_activity(a) for a in args.activity] if args.activity else None

    progress = parse_progress(args.progress) if args.progress is not None else None

    # --progress-label defaults to "总进度" for initial; --status defaults to "active" / "运行中".
    progress_label = args.progress_label if args.progress_label is not _UNSET else "总进度"
    status = args.status if args.status is not None else "active"
    status_text = args.status_text if args.status_text is not None else "运行中"

    return render_initial(
        title=args.title,
        metrics=metrics,
        progress=progress,
        progress_label=progress_label,
        status=status,
        status_text=status_text,
        surface_id=args.surface,
        activity=activity,
    )


def cmd_update(args: argparse.Namespace) -> dict:
    metrics = dict(parse_metric(m) for m in args.metric) if args.metric else None

    progress = parse_progress(args.progress) if args.progress is not None else None
    # --progress-label: None means "don't touch the label" (only update progress value).
    progress_label = None if args.progress_label is _UNSET else args.progress_label

    return render_incremental(
        metrics=metrics,
        progress=progress,
        progress_label=progress_label,
        status=args.status,
        status_text=args.status_text,
        surface_id=args.surface,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="a2ui_render",
        description="Generate A2UI JSON from business data.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # Common parent for shared flags
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--surface", default="main", help="Surface ID (default: main)")
    common.add_argument("--title", help="Card title (required for initial)")
    common.add_argument("--status", choices=["active", "idle", "error"], help="Status value")
    common.add_argument("--status-text", dest="status_text", help="Status display text")
    common.add_argument("--progress", help="Progress 0.0-1.0")
    common.add_argument("--progress-label", dest="progress_label", default=_UNSET, help="Progress label text (default: 总进度 for initial; not touched for update)")
    common.add_argument("--metric", action="append", help="Metric as label=value (repeatable)")
    common.add_argument("--activity", action="append", help="Activity as time|text (repeatable)")
    common.add_argument("--output", "-o", help="Output file (default: stdout)")
    common.add_argument("--stats", action="store_true", help="Print payload stats to stderr")

    sub.add_parser("initial", parents=[common], help="Render initial dashboard")
    sub.add_parser("update", parents=[common], help="Render incremental update")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # --title is required for `initial` (Card title is part of the rendered UI).
    # We can't enforce this via argparse (subparsers can't share required flags
    # cleanly), so validate here for a friendly error instead of silently
    # emitting `"title": null`.
    if args.cmd == "initial" and not args.title:
        parser.error("--title is required for 'initial'")

    try:
        if args.cmd == "initial":
            payload = cmd_initial(args)
        elif args.cmd == "update":
            payload = cmd_update(args)
        else:
            parser.error(f"Unknown command: {args.cmd}")
            return 2
    except ValueError as e:
        # Validation errors (e.g. progress out of range, bad metric format).
        # Surface as a single-line stderr message instead of a Python traceback
        # so Agent callers can react programmatically.
        print(f"error: {e}", file=sys.stderr)
        return 2

    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.stats:
        stats = payload_stats(payload)
        print(f"[stats] bytes={stats['bytes']} chars={stats['chars']} tokens_est={stats['tokens_est']}",
              file=sys.stderr)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())