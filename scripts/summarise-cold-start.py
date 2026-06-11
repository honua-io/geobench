#!/usr/bin/env python3
"""Print a Markdown summary table from a cold-start result JSON file.

Usage:
  python3 scripts/summarise-cold-start.py results/<ts>/honua-cold-start.json
"""
import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: summarise-cold-start.py <cold-start.json>", file=sys.stderr)
        return 1

    path = sys.argv[1]
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception as exc:
        print(f"ERROR reading {path}: {exc}", file=sys.stderr)
        return 1

    h = d.get("cold_start_healthy", {})
    r = d.get("cold_start_first_request", {})

    def fmt(v: object) -> str:
        return str(v) if v is not None else "—"

    print("| Metric | Median (ms) | Min (ms) | Max (ms) |")
    print("|--------|------------:|---------:|---------:|")
    print(f"| Healthy | {fmt(h.get('median_ms'))} | {fmt(h.get('min_ms'))} | {fmt(h.get('max_ms'))} |")
    print(f"| First request | {fmt(r.get('median_ms'))} | {fmt(r.get('min_ms'))} | {fmt(r.get('max_ms'))} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
