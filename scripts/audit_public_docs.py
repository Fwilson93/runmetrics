#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

DOCS = Path("docs")

# These are actual key names that should never appear in public JSON.
# We scan JSON structurally for these keys, rather than failing on harmless
# explanatory text such as "GPS is used locally only".
FORBIDDEN_JSON_KEYS = {
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "bearer",
    "summary_polyline",
    "polyline",
    "latlng",
    "start_latlng",
    "end_latlng",
    "latitude",
    "longitude",
    "lat",
    "lng",
    "activity_id",
    "athlete_id",
    "external_id",
    "upload_id",
    "map",
}

# These are sensitive textual patterns that should fail anywhere, including
# HTML/JS/CSS/JSON. This intentionally does NOT include words like "GPS",
# "route", or "activity IDs" because those can appear in safe privacy notes.
FORBIDDEN_TEXT_PATTERNS = [
    r"access_token",
    r"refresh_token",
    r"client_secret",
    r"Authorization\s*:",
    r"Bearer\s+[A-Za-z0-9_\-\.]+",
    r"summary_polyline",
    r"start_latlng",
    r"end_latlng",
    r"external_id",
    r"upload_id",
]

TEXT_RX = re.compile("|".join(FORBIDDEN_TEXT_PATTERNS), re.IGNORECASE)


def is_coordinate_pair(value: Any) -> bool:
    """
    Conservative coordinate-pair detector.

    This only flags obvious [lat, lon] pairs. It should not trigger on normal
    chart pairs because those are usually not two raw floats in geographic ranges.
    """
    if not isinstance(value, list) or len(value) != 2:
        return False

    a, b = value

    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False

    lat = float(a)
    lon = float(b)

    return -90 <= lat <= 90 and -180 <= lon <= 180


def scan_json(obj: Any, path: str, problems: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()

            if key_l in FORBIDDEN_JSON_KEYS:
                problems.append(f"{path}: forbidden public JSON key: {key}")

            scan_json(value, f"{path}.{key}", problems)

    elif isinstance(obj, list):
        if is_coordinate_pair(obj):
            problems.append(f"{path}: possible raw coordinate pair in public JSON")

        for i, value in enumerate(obj):
            scan_json(value, f"{path}[{i}]", problems)

    elif isinstance(obj, str):
        if TEXT_RX.search(obj):
            problems.append(f"{path}: forbidden sensitive text pattern in JSON string")


def scan_text_file(path: Path, problems: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(text.splitlines(), start=1):
        if TEXT_RX.search(line):
            problems.append(f"{path}:{i}: forbidden sensitive text pattern: {line[:220]}")


def main() -> int:
    if not DOCS.exists():
        print("ERROR: docs/ does not exist.")
        return 1

    problems: list[str] = []

    for path in DOCS.rglob("*"):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()

        if suffix == ".json":
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                problems.append(f"{path}: invalid JSON: {exc}")
                continue

            scan_json(obj, str(path), problems)

        elif suffix in {".html", ".js", ".css", ".txt"}:
            scan_text_file(path, problems)

    if problems:
        print("ERROR: public docs privacy audit failed.")
        for p in problems[:200]:
            print(p)
        if len(problems) > 200:
            print(f"... plus {len(problems) - 200} more")
        return 1

    print("OK: public docs privacy audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
