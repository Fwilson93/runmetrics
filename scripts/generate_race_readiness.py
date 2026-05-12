#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
CONFIG = ROOT / "config" / "runmetrics_config.json"
HISTORY = DATA / "race_predictions_history.json"

DISTANCES = {
    "5K": 5.0,
    "10K": 10.0,
    "Half marathon": 21.0975,
    "Marathon": 42.195,
}

DEFAULT_READINESS = {
    "5K": {"min_recent_long_run_km": 5, "min_28d_distance_km": 20},
    "10K": {"min_recent_long_run_km": 9, "min_28d_distance_km": 35},
    "Half marathon": {"min_recent_long_run_km": 16, "min_28d_distance_km": 70},
    "Marathon": {"min_recent_long_run_km": 28, "min_28d_distance_km": 150},
}

# Threshold-pace multipliers. Lower pace = faster.
PACE_FACTORS = {
    "5K": (0.90, 0.95),
    "10K": (0.95, 1.00),
    "Half marathon": (1.03, 1.09),
    "Marathon": (1.13, 1.24),
}

RIEGEL_EXPONENT = 1.06


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


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


def fnum(x: Any, default: float = 0.0) -> float:
    return float(x) if finite(x) else default


def clean(x: Any, nd: int = 1):
    return round(float(x), nd) if finite(x) else None


def format_time(seconds: Any) -> str | None:
    """
    mm:ss under 1 hour; h:mm:ss for 1 hour or more.
    """
    if not finite(seconds):
        return None
    s = int(round(float(seconds)))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def latest_threshold(threshold: dict[str, Any]) -> dict[str, Any] | None:
    if threshold.get("latest"):
        return threshold["latest"]
    items = threshold.get("items") or []
    return items[-1] if items else None


def get_config() -> dict[str, Any]:
    cfg = read_json(CONFIG, {}) or {}
    rr = cfg.setdefault("race_readiness", {})
    for race, vals in DEFAULT_READINESS.items():
        rr.setdefault(race, vals.copy())
        for k, v in vals.items():
            rr[race].setdefault(k, v)
    write_json(CONFIG, cfg)
    return cfg


def activity_time_sec(activity: dict[str, Any]) -> float | None:
    dist = fnum(activity.get("distance_km"), 0)
    moving_min = fnum(activity.get("moving_time_min"), 0)
    pace = activity.get("pace_min_per_km")

    if dist > 0 and moving_min > 0:
        return moving_min * 60.0

    if dist > 0 and finite(pace):
        return float(pace) * 60.0 * dist

    return None


def observed_equivalent_estimates(activities: list[dict[str, Any]], target_km: float) -> list[dict[str, Any]]:
    """
    Convert recent activities into rough target-distance equivalents.

    Rules:
    - If activity is at least 65% of target distance, allow Riegel-style extrapolation.
    - If activity is longer than target, use the whole-activity average pace as conservative evidence.
    - Ignore very short activities for longer race predictions.
    """
    estimates = []

    for a in activities:
        d = fnum(a.get("distance_km"), 0)
        t = activity_time_sec(a)
        if d <= 0 or not finite(t):
            continue

        if d < target_km * 0.65:
            continue

        # Riegel equivalent. For longer-than-target runs, this is usually conservative enough
        # because it uses average pace for the whole run.
        est = float(t) * ((target_km / d) ** RIEGEL_EXPONENT)

        estimates.append({
            "date": a.get("date"),
            "source_distance_km": clean(d, 2),
            "source_time_sec": clean(t, 0),
            "source_time": format_time(t),
            "estimated_time_sec": clean(est, 0),
            "estimated_time": format_time(est),
        })

    return sorted(estimates, key=lambda x: x["estimated_time_sec"] if x["estimated_time_sec"] is not None else 10**9)


def threshold_estimates(threshold_latest_obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not threshold_latest_obj:
        return None

    threshold_pace = threshold_latest_obj.get("threshold_pace_proxy_min_per_km")
    if not finite(threshold_pace):
        return None

    threshold_pace = float(threshold_pace)
    out = {}

    for race, dist in DISTANCES.items():
        lo, hi = PACE_FACTORS[race]
        fast_pace = threshold_pace * lo
        slow_pace = threshold_pace * hi
        fast_sec = fast_pace * 60.0 * dist
        slow_sec = slow_pace * 60.0 * dist

        out[race] = {
            "source": "threshold_proxy",
            "distance_km": dist,
            "fast_time_sec": clean(fast_sec, 0),
            "slow_time_sec": clean(slow_sec, 0),
            "fast_time": format_time(fast_sec),
            "slow_time": format_time(slow_sec),
            "pace_range_min_per_km": [clean(fast_pace, 2), clean(slow_pace, 2)],
        }

    return out


def blended_fitness_estimate(race: str, target_km: float, threshold_fit: dict[str, Any] | None, observed: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Build a range using both threshold-derived and observed performance-derived evidence.
    If observed performances are faster than threshold estimate, the range reflects that.
    """
    candidates = []

    if threshold_fit:
        if finite(threshold_fit.get("fast_time_sec")):
            candidates.append({
                "source": "threshold_proxy_fast",
                "time_sec": float(threshold_fit["fast_time_sec"]),
            })
        if finite(threshold_fit.get("slow_time_sec")):
            candidates.append({
                "source": "threshold_proxy_slow",
                "time_sec": float(threshold_fit["slow_time_sec"]),
            })

    for o in observed[:5]:
        if finite(o.get("estimated_time_sec")):
            candidates.append({
                "source": "observed_activity",
                "time_sec": float(o["estimated_time_sec"]),
                "source_date": o.get("date"),
                "source_distance_km": o.get("source_distance_km"),
            })

    if not candidates:
        return None

    times = sorted(c["time_sec"] for c in candidates)
    best_observed = observed[0] if observed else None

    # Fast end: best of all evidence.
    fast = min(times)

    # Slow end: avoid silly-wide ranges. Use slower threshold estimate if available,
    # otherwise add an uncertainty band to observed estimate.
    if threshold_fit and finite(threshold_fit.get("slow_time_sec")):
        slow = max(fast * 1.03, float(threshold_fit["slow_time_sec"]))
    else:
        slow = fast * 1.08

    # If observed evidence beats threshold by a lot, keep the slow end closer to observed
    # so the displayed range doesn't contradict known performances too badly.
    if best_observed and threshold_fit and finite(threshold_fit.get("fast_time_sec")):
        obs = float(best_observed["estimated_time_sec"])
        thr_fast = float(threshold_fit["fast_time_sec"])
        if obs < thr_fast:
            slow = min(slow, obs * 1.08)

    sources = sorted(set(c["source"] for c in candidates))

    return {
        "distance_km": target_km,
        "fast_time_sec": clean(fast, 0),
        "slow_time_sec": clean(slow, 0),
        "fast_time": format_time(fast),
        "slow_time": format_time(slow),
        "sources": sources,
        "best_observed_equivalent": best_observed,
        "note": "Range blends threshold-proxy estimate with recent observed activity equivalents; readiness is assessed separately.",
    }


def longest_run(activities: list[dict[str, Any]]) -> float:
    return max([fnum(a.get("distance_km"), 0) for a in activities] or [0.0])


def count_runs_over(activities: list[dict[str, Any]], km: float) -> int:
    return sum(1 for a in activities if fnum(a.get("distance_km"), 0) >= km)


def readiness_for(race: str, activities: list[dict[str, Any]], summary: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    rules = cfg["race_readiness"][race]
    dist = DISTANCES[race]
    long_km = longest_run(activities)
    d28 = fnum(summary.get("last_28d_distance_km"), 0)
    min_long = float(rules["min_recent_long_run_km"])
    min28 = float(rules["min_28d_distance_km"])

    long_ratio = long_km / min_long if min_long else 1
    vol_ratio = d28 / min28 if min28 else 1

    if long_ratio >= 1 and vol_ratio >= 1:
        verdict = "ready"
        limiter = "No obvious distance-specific limiter from current public-safe data."
    elif long_ratio >= 0.8 and vol_ratio >= 0.75:
        verdict = "mostly ready"
        limiter = "Close to the distance-specific guardrails, but confidence would improve with more specific volume."
    elif long_ratio >= 0.6 or vol_ratio >= 0.6:
        verdict = "plausible but durability-limited"
        limiter = "Fitness may exist, but recent long-run or 28-day volume is below the configured readiness guardrail."
    else:
        verdict = "not distance-ready"
        limiter = "Current data does not show enough distance-specific preparation; you probably should not trust the fitness estimate for this distance yet."

    return {
        "verdict": verdict,
        "limiter": limiter,
        "longest_recent_run_km": clean(long_km, 1),
        "last_28d_distance_km": clean(d28, 1),
        "required_long_run_km": min_long,
        "required_28d_distance_km": min28,
        "runs_over_65pct_distance": count_runs_over(activities, dist * 0.65),
    }


def build_training_priorities(summary, run_types, eff, fade, matched_v, activities):
    out = []
    long_km = longest_run(activities)
    tsb = fnum(summary.get("tsb"), 0)
    acwr = fnum(summary.get("acwr"), 1)
    hard = int(fnum(run_types.get("recent_28_hard_count"), 0))
    fade_val = fade.get("recent_mean_efficiency_change_pct")
    eff_verdict = eff.get("verdict")
    best = (matched_v.get("best_signal") or {}) if isinstance(matched_v, dict) else {}

    if long_km < 14:
        out.append({
            "rank": 1,
            "area": "Long-run durability",
            "status": "weak point",
            "message": f"Longest recent run is {clean(long_km,1)} km, so longer-race readiness is likely the main limiter.",
            "suggestion": "Build long-run exposure gradually before trusting longer-distance race predictions.",
        })
    elif long_km < 20:
        out.append({
            "rank": 1,
            "area": "Durability",
            "status": "watch",
            "message": f"Longest recent run is {clean(long_km,1)} km: solid for shorter races, but still a limiter for marathon-specific confidence.",
            "suggestion": "Keep extending long runs carefully while protecting easy days.",
        })

    if tsb < -15 or acwr > 1.4:
        out.append({
            "rank": len(out) + 1,
            "area": "Load management",
            "status": "caution",
            "message": f"Load signals suggest caution: TSB {clean(tsb,1)}, ACWR {clean(acwr,2)}.",
            "suggestion": "Prioritise consolidation and easy running over adding another hard session.",
        })

    if finite(fade_val) and float(fade_val) < -5:
        out.append({
            "rank": len(out) + 1,
            "area": "Steady-run fade",
            "status": "weak point",
            "message": f"Recent steady-run fade averages {clean(fade_val,1)}%, suggesting durability/fatigue may be limiting longer efforts.",
            "suggestion": "Use easy endurance runs and fuelling/hydration practice before adding much intensity.",
        })

    if eff_verdict in {"worsening", "not enough data"}:
        out.append({
            "rank": len(out) + 1,
            "area": "Easy-run efficiency",
            "status": eff_verdict,
            "message": "Easy/steady speed per heartbeat is not clearly improving yet." if eff_verdict == "worsening" else "There is not enough clean easy/steady efficiency data yet.",
            "suggestion": "Keep easy runs genuinely easy and collect more comparable HR data.",
        })
    elif eff_verdict == "improving":
        out.append({
            "rank": len(out) + 1,
            "area": "Aerobic efficiency",
            "status": "strength",
            "message": "Easy/steady speed per heartbeat appears to be improving.",
            "suggestion": "Maintain consistency; avoid over-testing this by turning easy runs into workouts.",
        })

    if hard >= 4:
        out.append({
            "rank": len(out) + 1,
            "area": "Hard/easy balance",
            "status": "watch",
            "message": f"There are {hard} hard-ish classified runs in the latest 28 classified runs.",
            "suggestion": "Make sure easy volume is not drifting into moderate effort too often.",
        })

    if best.get("efficiency_change_pct") is not None:
        out.append({
            "rank": len(out) + 1,
            "area": "Matched-route efficiency",
            "status": "signal",
            "message": f"Best matched-route signal is {best.get('efficiency_change_pct')}% speed per heartbeat.",
            "suggestion": "Use this as route-specific evidence, but keep broader easy-efficiency and durability signals in view.",
        })

    if not out:
        out.append({
            "rank": 1,
            "area": "Consistency",
            "status": "default priority",
            "message": f"Recent load is {clean(summary.get('last_7d_distance_km'),1)} km in 7 days and {clean(summary.get('last_28d_distance_km'),1)} km in 28 days.",
            "suggestion": "Keep building consistently; no single weak point is dominant from the current public-safe metrics.",
        })

    for i, p in enumerate(out[:5], 1):
        p["rank"] = i

    return {
        "generated_at_utc": now(),
        "method": "Rule-based priorities from public-safe load, run-type, efficiency, matched-route and steady-run fade summaries.",
        "items": out[:5],
    }


def race_predictions(summary, activities, threshold, cfg):
    th = latest_threshold(threshold)
    threshold_fit = threshold_estimates(th)
    items = []

    for race, dist in DISTANCES.items():
        observed = observed_equivalent_estimates(activities, dist)
        th_fit = threshold_fit.get(race) if threshold_fit else None
        fit = blended_fitness_estimate(race, dist, th_fit, observed)
        ready = readiness_for(race, activities, summary, cfg)

        confidence = "low"
        if fit and ready["verdict"] in {"ready", "mostly ready"}:
            confidence = "medium"
        if fit and ready["verdict"] == "ready" and race in {"5K", "10K"}:
            confidence = "medium-high"
        if race == "Marathon" and ready["verdict"] != "ready":
            confidence = "low"

        items.append({
            "race": race,
            "distance_km": dist,
            "fitness_estimate": fit,
            "threshold_estimate": th_fit,
            "observed_equivalents": observed[:5],
            "readiness": ready,
            "confidence": confidence,
            "interpretation": "Fitness estimate blends threshold proxy and recent observed activity equivalents; readiness separately checks whether recent distance-specific training supports actually racing that far.",
        })

    return {
        "generated_at_utc": now(),
        "date": today(),
        "method": "Transparent heuristic. Fitness estimates blend threshold pace proxy with recent observed activity equivalents. Readiness is separately gated by longest recent run and 28-day volume. This is not a guarantee of race performance.",
        "threshold_anchor": th,
        "items": items,
    }


def update_history(pred):
    hist = read_json(HISTORY, {"items": []}) or {"items": []}
    items = [x for x in (hist.get("items") or []) if x.get("date") != pred["date"]]

    for p in pred.get("items") or []:
        f = p.get("fitness_estimate") or {}
        items.append({
            "date": pred["date"],
            "race": p.get("race"),
            "fast_time_sec": f.get("fast_time_sec"),
            "slow_time_sec": f.get("slow_time_sec"),
            "fast_time": f.get("fast_time"),
            "slow_time": f.get("slow_time"),
            "readiness": (p.get("readiness") or {}).get("verdict"),
            "confidence": p.get("confidence"),
        })

    hist = {
        "generated_at_utc": now(),
        "method": "Daily snapshots of derived race-fitness estimates and readiness verdicts. Public-safe; no GPS or activity IDs.",
        "items": sorted(items, key=lambda x: (x.get("date", ""), x.get("race", ""))),
    }
    write_json(HISTORY, hist)
    return hist


def main():
    cfg = get_config()
    summary = read_json(DATA / "summary.json", {}) or {}
    activities = read_json(DATA / "activities_recent.json", []) or []
    threshold = read_json(DATA / "threshold_history.json", {"items": []}) or {"items": []}
    fade = read_json(DATA / "steady_fade_verdict.json", {}) or {}
    eff = read_json(DATA / "efficiency_trends.json", {}) or {}
    matched = read_json(DATA / "matched_route_verdicts.json", {}) or {}
    run_types = read_json(DATA / "run_types.json", {}) or {}

    pr = build_training_priorities(summary, run_types, eff, fade, matched, activities)
    pred = race_predictions(summary, activities, threshold, cfg)
    hist = update_history(pred)

    write_json(DATA / "training_priorities.json", pr)
    write_json(DATA / "race_predictions.json", pred)

    insights = read_json(DATA / "insights.json", {}) or {}
    insights.update({
        "training_priorities": pr,
        "race_predictions": pred,
        "race_predictions_history": hist,
        "generated_at_utc": now(),
    })
    write_json(DATA / "insights.json", insights)

    print("[race-readiness] wrote observed+threshold race predictions")


if __name__ == "__main__":
    main()
