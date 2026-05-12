#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "runmetrics_config.json"
MATCHER = ROOT / "scripts" / "match_runs_by_gps_efficiency.py"


def read_config():
    if not CONFIG.exists():
        return {}
    with CONFIG.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    if not MATCHER.exists():
        print("[gps-config] match_runs_by_gps_efficiency.py not found; skipping GPS matching.")
        return 0

    cfg = read_config().get("gps_matching", {})

    threshold_m = str(cfg.get("threshold_m", 90))
    min_group_size = str(cfg.get("min_group_size", 2))
    n_points = str(cfg.get("n_points", 80))

    cmd = [
        sys.executable,
        str(MATCHER),
        "--threshold-m", threshold_m,
        "--min-group-size", min_group_size,
        "--n-points", n_points,
    ]

    print("[gps-config] " + " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
