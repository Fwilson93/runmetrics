#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
PRED = DATA / "race_predictions.json"
HIST = DATA / "race_predictions_history.json"
PRIORITIES = DATA / "training_priorities.json"
SUMMARY = DATA / "summary.json"
RUN_TYPES = DATA / "run_types.json"
FADE = DATA / "steady_fade_verdict.json"
EFF = DATA / "efficiency_trends.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def clean(x: Any, nd: int = 1):
    return round(float(x), nd) if finite(x) else None


def format_delta(seconds: float | None) -> str:
    if seconds is None or not finite(seconds):
        return "—"
    sign = "+" if seconds > 0 else ""
    s = abs(int(round(seconds)))
    m = s // 60
    sec = s % 60
    if m:
        return f"{sign}{'-' if seconds < 0 else ''}{m}:{sec:02d}"
    return f"{sign}{'-' if seconds < 0 else ''}{sec}s"


def midpoint(item: dict[str, Any]) -> float | None:
    if finite(item.get("fast_time_sec")) and finite(item.get("slow_time_sec")):
        return (float(item["fast_time_sec"]) + float(item["slow_time_sec"])) / 2.0
    return None


def trend_for(race: str, current_mid: float | None, current_date: str, history_items: list[dict[str, Any]]) -> dict[str, Any]:
    if current_mid is None:
        return {
            "label": "no estimate",
            "message": "No current estimate is available yet.",
            "change_sec": None,
            "change_pct": None,
            "previous_date": None,
        }

    previous = [x for x in history_items if x.get("race") == race and x.get("date") != current_date and finite(x.get("fast_time_sec")) and finite(x.get("slow_time_sec"))]
    previous = sorted(previous, key=lambda x: x.get("date", ""))
    if not previous:
        return {
            "label": "new baseline",
            "message": "This is the first stored estimate for this distance, so there is no trend yet.",
            "change_sec": None,
            "change_pct": None,
            "previous_date": None,
        }

    prev = previous[-1]
    prev_mid = midpoint(prev)
    if prev_mid is None or prev_mid == 0:
        return {
            "label": "new baseline",
            "message": "Previous estimate was incomplete, so trend is not available yet.",
            "change_sec": None,
            "change_pct": None,
            "previous_date": prev.get("date"),
        }

    delta = current_mid - prev_mid
    pct = (delta / prev_mid) * 100.0
    # Negative delta = faster estimate = improving.
    if pct <= -1.5:
        label = "improving"
        msg = f"Estimate is faster than the previous stored snapshot by about {format_delta(delta)}."
    elif pct >= 1.5:
        label = "worsening"
        msg = f"Estimate is slower than the previous stored snapshot by about {format_delta(delta)}."
    else:
        label = "stable"
        msg = f"Estimate is broadly unchanged versus the previous stored snapshot ({format_delta(delta)})."

    return {
        "label": label,
        "message": msg,
        "change_sec": clean(delta, 0),
        "change_pct": clean(pct, 1),
        "previous_date": prev.get("date"),
    }


def focus_for(pred: dict[str, Any], priorities: dict[str, Any], summary: dict[str, Any], run_types: dict[str, Any], fade: dict[str, Any], eff: dict[str, Any]) -> dict[str, Any]:
    race = pred.get("race")
    readiness = (pred.get("readiness") or {}).get("verdict")
    longest = (pred.get("readiness") or {}).get("longest_recent_run_km")
    required_long = (pred.get("readiness") or {}).get("required_long_run_km")
    d28 = (pred.get("readiness") or {}).get("last_28d_distance_km")
    required_28 = (pred.get("readiness") or {}).get("required_28d_distance_km")
    hard_count = run_types.get("recent_28_hard_count")
    fade_label = fade.get("label")
    eff_verdict = eff.get("verdict")

    # Race-specific emphasis. Keep this deliberately conservative.
    if readiness in {"not distance-ready", "plausible but durability-limited"}:
        return {
            "primary": "Build distance-specific durability",
            "rationale": f"Readiness is {readiness}. Longest recent run is {longest} km versus a guardrail of {required_long} km; 28-day volume is {d28} km versus {required_28} km.",
            "training_emphasis": "Prioritise consistent easy volume and gradually extending the long run before relying on the predicted time.",
        }

    if race in {"5K", "10K"}:
        if eff_verdict == "worsening":
            return {
                "primary": "Rebuild aerobic efficiency",
                "rationale": "Easy/steady speed per heartbeat is worsening, which can cap shorter-race improvements despite decent speed.",
                "training_emphasis": "Keep easy runs genuinely easy, then add one controlled quality session when load is stable.",
            }
        return {
            "primary": "Improve threshold / speed endurance",
            "rationale": f"Readiness is {readiness}. For {race}, the biggest gain is likely from controlled quality rather than simply adding long-run distance.",
            "training_emphasis": "Use threshold intervals, short tempo blocks, strides, and enough easy volume to absorb them.",
        }

    if race == "Half marathon":
        if fade_label in {"noticeable fade", "strong fade"}:
            return {
                "primary": "Improve durability under steady effort",
                "rationale": f"Steady-run fade is currently labelled '{fade_label}', which matters for half-marathon performance.",
                "training_emphasis": "Progress long easy runs and add controlled steady/tempo segments only when fatigue is manageable.",
            }
        return {
            "primary": "Extend sustained aerobic strength",
            "rationale": f"Readiness is {readiness}. The half marathon benefits from both long-run exposure and threshold durability.",
            "training_emphasis": "Build long-run consistency plus one moderate sustained-effort workout most weeks.",
        }

    if race == "Marathon":
        return {
            "primary": "Increase marathon-specific volume and long-run exposure",
            "rationale": f"Marathon readiness is {readiness}; longest recent run and 28-day volume are the key guardrails here.",
            "training_emphasis": "Build weekly volume, long runs, and fuelling practice before treating the marathon estimate as actionable.",
        }

    return {
        "primary": "Maintain consistency",
        "rationale": "No dominant limiter was identified from the current public-safe metrics.",
        "training_emphasis": "Keep training consistent and reassess after more comparable data accumulates.",
    }


def main() -> int:
    pred = read_json(PRED, {}) or {}
    hist = read_json(HIST, {"items": []}) or {"items": []}
    priorities = read_json(PRIORITIES, {"items": []}) or {"items": []}
    summary = read_json(SUMMARY, {}) or {}
    run_types = read_json(RUN_TYPES, {}) or {}
    fade = read_json(FADE, {}) or {}
    eff = read_json(EFF, {}) or {}

    current_date = pred.get("date")
    history_items = hist.get("items") or []

    for item in pred.get("items") or []:
        fit = item.get("fitness_estimate") or {}
        cur_mid = midpoint(fit)
        item["trend"] = trend_for(item.get("race"), cur_mid, current_date, history_items)
        item["training_focus"] = focus_for(item, priorities, summary, run_types, fade, eff)

    pred["trend_method"] = "Trend compares the midpoint of today's estimated range with the previous stored snapshot for the same race. Negative time change means faster/improving."
    pred["training_focus_method"] = "Training focus is rule-based from readiness, long-run exposure, 28-day volume, fade, run-type balance and easy-efficiency trend."
    pred["enhanced_at_utc"] = now_iso()
    write_json(PRED, pred)

    # Also update insights if present.
    insights_path = DATA / "insights.json"
    insights = read_json(insights_path, {}) or {}
    insights["race_predictions"] = pred
    insights["generated_at_utc"] = now_iso()
    write_json(insights_path, insights)

    print("[race-enhance] added trends and training focus to docs/data/race_predictions.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
