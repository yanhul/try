#!/usr/bin/env python3
"""Discover a bounded crypto universe from TradingView and persist a raw snapshot."""
from __future__ import annotations

import argparse

from engine.universe_discovery import discover_crypto_universe, persist_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="JSON snapshot path")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    frame, snapshot = discover_crypto_universe(limit=args.limit)
    path = persist_snapshot(frame, snapshot, args.out)
    print(f"DISCOVERY PASS: {snapshot.row_count} rows")
    print(f"symbols={len(snapshot.symbols)}")
    print(f"sha256={snapshot.payload_sha256}")
    print(f"snapshot={path}")


if __name__ == "__main__":
    main()
