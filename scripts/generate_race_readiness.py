#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
CONFIG = ROOT / "config" / "runmetrics_config.json"
HISTORY = DATA / "race_predictions_history.json"

# Explicit display/calculation order.
RACES = [
    ("5K", 5.0, "5K"),
    ("10K", 10.0, "10K"),
    ("1/2M", 21.0975, "Half marathon"),
    ("Marathon", 42.195, "Marathon"),
    ("50K", 50.0, "50K"),
    ("100K", 100.0, "100K"),
]

DEFAULT_READINESS = {
    "5K": {"min_recent_long_run_km": 5, "min_28d_distance_km": 20},
    "10K": {"min_recent_long_run_km": 9, "min_28d_distance_km": 35},
    "1/2M": {"min_recent_long_run_km": 16, "min_28d_distance_km": 70},
    "Marathon": {"min_recent_long_run_km": 28, "min_28d_distance_km": 150},
    "50K": {"min_recent_long_run_km": 35, "min_28d_distance_km": 180},
    "100K": {"min_recent_long_run_km": 50, "min_28d_distance_km": 260},
}

# Multipliers applied to threshold pace. Lower pace = faster.
PACE_FACTORS = {
    "5K": (0.90, 0.95),
    "10K": (0.95, 1.00),
    "1/2M": (1.03, 1.09),
    "Marathon": (1.13, 1.24),
    "50K": (1.22, 1.40),
    "100K": (1.45, 1.85),
}

RIEGEL_EXPONENT = 1.06


def now_iso() -> str:
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
    """mm:ss under 1 hour; h:mm:ss for 1 hour or more."""
    if not finite(seconds):
        return None
    s = int(round(float(seconds)))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def parse_date(value: Any):
    if not value:
        return None
    try:
        # date-only or ISO both OK.
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None


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


def activity_distance_km(a: dict[str, Any]) -> float:
    if finite(a.get("distance_km")):
        return float(a["distance_km"])
    if finite(a.get("distance")):
        return float(a["distance"]) / 1000.0
    return 0.0


def activity_time_sec(a: dict[str, Any]) -> float | None:
    # Prefer explicit minutes if public static export has it.
    for key in ["moving_time_min", "duration_min"]:
        if finite(a.get(key)) and float(a[key]) > 0:
            return float(a[key]) * 60.0
    # Strava-style seconds if present.
    for key in ["moving_time", "elapsed_time"]:
        if finite(a.get(key)) and float(a[key]) > 0:
            return float(a[key])
    # Fallback to pace * distance.
    d = activity_distance_km(a)
    if d > 0 and finite(a.get("pace_min_per_km")):
        return float(a["pace_min_per_km"]) * 60.0 * d
    return None


def equivalent_time(source_sec: float, source_km: float, target_km: float) -> float:
    return source_sec * ((target_km / source_km) ** RIEGEL_EXPONENT)


def observed_equivalents(activities: list[dict[str, Any]], target_km: float, window: tuple[Any, Any] | None = None) -> list[dict[str, Any]]:
    out = []
    start, end = window if window else (None, None)
    for a in activities:
        dte = parse_date(a.get("date") or a.get("start_date"))
        if start and dte and dte < start:
            continue
        if end and dte and dte > end:
            continue
        d = activity_distance_km(a)
        t = activity_time_sec(a)
        if d <= 0 or not finite(t):
            continue

        # For 5K, directly use any activity around/over 5K. This catches real sub-20 5Ks.
        # For longer races, require enough distance-specific evidence to extrapolate.
        if target_km <= 10:
            min_source = min(target_km * 0.80, target_km - 0.1)
        elif target_km <= 21.2:
            min_source = target_km * 0.65
        elif target_km <= 50:
            min_source = target_km * 0.50
        else:
            min_source = target_km * 0.35
        if d < min_source:
            continue

        est = equivalent_time(float(t), d, target_km)
        out.append({
            "date": dte.isoformat() if dte else a.get("date"),
            "source_distance_km": clean(d, 2),
            "source_time_sec": clean(t, 0),
            "source_time": format_time(t),
            "estimated_time_sec": clean(est, 0),
            "estimated_time": format_time(est),
        })
    return sorted(out, key=lambda x: x.get("estimated_time_sec") if x.get("estimated_time_sec") is not None else 10**12)


def threshold_estimates(threshold_latest_obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not threshold_latest_obj or not finite(threshold_latest_obj.get("threshold_pace_proxy_min_per_km")):
        return None
    tp = float(threshold_latest_obj["threshold_pace_proxy_min_per_km"])
    out = {}
    for race, dist, _ in RACES:
        lo, hi = PACE_FACTORS[race]
        fp, sp = tp * lo, tp * hi
        fs, ss = fp * 60 * dist, sp * 60 * dist
        out[race] = {
            "source": "threshold_proxy",
            "distance_km": dist,
            "fast_time_sec": clean(fs, 0),
            "slow_time_sec": clean(ss, 0),
            "fast_time": format_time(fs),
            "slow_time": format_time(ss),
            "pace_range_min_per_km": [clean(fp, 2), clean(sp, 2)],
        }
    return out


def blended_estimate(race: str, target_km: float, threshold_fit: dict[str, Any] | None, observed: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    if threshold_fit:
        if finite(threshold_fit.get("fast_time_sec")):
            candidates.append(("threshold_proxy_fast", float(threshold_fit["fast_time_sec"])))
        if finite(threshold_fit.get("slow_time_sec")):
            candidates.append(("threshold_proxy_slow", float(threshold_fit["slow_time_sec"])))
    for o in observed[:8]:
        if finite(o.get("estimated_time_sec")):
            candidates.append(("observed_activity", float(o["estimated_time_sec"])))
    if not candidates:
        return None

    best_obs = observed[0] if observed else None
    fast = min(v for _, v in candidates)

    # If there is direct-ish observed evidence, do not let threshold-only estimate hide it.
    if best_obs and finite(best_obs.get("estimated_time_sec")):
        obs = float(best_obs["estimated_time_sec"])
        # Range around observed best; broader for longer races.
        band = 1.06 if target_km <= 10 else 1.08 if target_km <= 21.2 else 1.12 if target_km <= 42.3 else 1.20
        fast = min(fast, obs)
        slow = max(fast * 1.03, min(max(v for _, v in candidates), obs * band))
    else:
        slow = max(v for _, v in candidates)

    if slow < fast:
        slow = fast * 1.05

    return {
        "distance_km": target_km,
        "fast_time_sec": clean(fast, 0),
        "slow_time_sec": clean(slow, 0),
        "fast_time": format_time(fast),
        "slow_time": format_time(slow),
        "sources": sorted(set(k for k, _ in candidates)),
        "best_observed_equivalent": best_obs,
        "note": "Range blends threshold proxy with recent observed activity equivalents. Readiness is assessed separately.",
    }


def longest_run(activities: list[dict[str, Any]]) -> float:
    return max([activity_distance_km(a) for a in activities] or [0.0])


def count_runs_over(activities: list[dict[str, Any]], km: float) -> int:
    return sum(1 for a in activities if activity_distance_km(a) >= km)


def readiness_for(race: str, target_km: float, activities: list[dict[str, Any]], summary: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    rules = cfg["race_readiness"][race]
    long_km = longest_run(activities)
    d28 = fnum(summary.get("last_28d_distance_km"), 0)
    min_long = float(rules["min_recent_long_run_km"])
    min28 = float(rules["min_28d_distance_km"])
    lr = long_km / min_long if min_long else 1
    vr = d28 / min28 if min28 else 1
    if lr >= 1 and vr >= 1:
        verdict = "ready"
        limiter = "No obvious distance-specific limiter from current public-safe data."
    elif lr >= 0.8 and vr >= 0.75:
        verdict = "mostly ready"
        limiter = "Close to the distance-specific guardrails, but confidence would improve with more specific volume."
    elif lr >= 0.6 or vr >= 0.6:
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
        "runs_over_65pct_distance": count_runs_over(activities, target_km * 0.65),
    }


def latest_activity_date(activities: list[dict[str, Any]]):
    dates = [parse_date(a.get("date") or a.get("start_date")) for a in activities]
    dates = [d for d in dates if d]
    return max(dates) if dates else datetime.now(timezone.utc).date()


def trend_from_three_months(race: str, target_km: float, current_estimate: dict[str, Any] | None, activities: list[dict[str, Any]]) -> dict[str, Any]:
    if not current_estimate or not finite(current_estimate.get("fast_time_sec")) or not finite(current_estimate.get("slow_time_sec")):
        return {"label": "no estimate", "message": "No current estimate is available yet.", "change_sec": None, "change_pct": None, "comparison": "three_month_performance_window"}
    latest = latest_activity_date(activities)
    current_start = latest - timedelta(days=45)
    old_start = latest - timedelta(days=120)
    old_end = latest - timedelta(days=75)

    old_obs = observed_equivalents(activities, target_km, (old_start, old_end))
    if not old_obs:
        return {"label": "new baseline", "message": "No comparable observed activity was found around three months ago.", "change_sec": None, "change_pct": None, "comparison": "three_month_performance_window"}

    current_mid = (float(current_estimate["fast_time_sec"]) + float(current_estimate["slow_time_sec"])) / 2
    old_best = float(old_obs[0]["estimated_time_sec"])
    delta = current_mid - old_best
    pct = (delta / old_best) * 100 if old_best else None
    if pct is not None and pct <= -1.5:
        label = "improving"
        msg = f"Current estimate is faster than the best comparable activity-derived estimate from roughly three months ago ({format_time(old_best)})."
    elif pct is not None and pct >= 1.5:
        label = "worsening"
        msg = f"Current estimate is slower than the best comparable activity-derived estimate from roughly three months ago ({format_time(old_best)})."
    else:
        label = "stable"
        msg = f"Current estimate is broadly similar to the best comparable activity-derived estimate from roughly three months ago ({format_time(old_best)})."
    return {
        "label": label,
        "message": msg,
        "change_sec": clean(delta, 0),
        "change_pct": clean(pct, 1),
        "comparison": "three_month_performance_window",
        "three_month_window": {"start": old_start.isoformat(), "end": old_end.isoformat()},
        "three_month_best_observed_equivalent": old_obs[0],
    }


def training_focus(race: str, readiness: dict[str, Any], fade: dict[str, Any], eff: dict[str, Any]) -> dict[str, Any]:
    verdict = readiness.get("verdict")
    if verdict in {"not distance-ready", "plausible but durability-limited"}:
        return {
            "primary": "Build distance-specific durability",
            "rationale": f"Readiness is {verdict}. Longest recent run is {readiness.get('longest_recent_run_km')} km versus a guardrail of {readiness.get('required_long_run_km')} km; 28-day volume is {readiness.get('last_28d_distance_km')} km versus {readiness.get('required_28d_distance_km')} km.",
            "training_emphasis": "Prioritise consistent easy volume and gradually extending the long run before relying on the predicted time.",
        }
    if race in {"5K", "10K"}:
        if eff.get("verdict") == "worsening":
            return {"primary": "Rebuild aerobic efficiency", "rationale": "Easy/steady speed per heartbeat is worsening.", "training_emphasis": "Keep easy runs genuinely easy, then add one controlled quality session when load is stable."}
        return {"primary": "Improve threshold / speed endurance", "rationale": f"Readiness is {verdict}. For {race}, the biggest gain is likely controlled quality rather than simply more distance.", "training_emphasis": "Use threshold intervals, short tempo blocks, strides, and enough easy volume to absorb them."}
    if race == "1/2M":
        return {"primary": "Extend sustained aerobic strength", "rationale": f"Readiness is {verdict}; half marathon performance depends on both long-run exposure and threshold durability.", "training_emphasis": "Build long-run consistency plus one moderate sustained-effort workout most weeks."}
    return {"primary": "Increase distance-specific volume and long-run exposure", "rationale": f"Readiness is {verdict}; longest recent run and 28-day volume are the key guardrails.", "training_emphasis": "Build weekly volume, long runs, and fuelling practice before treating the estimate as actionable."}


def build_training_priorities(summary, run_types, eff, fade, matched_v, activities):
    out = []
    long_km = longest_run(activities)
    tsb = fnum(summary.get("tsb"), 0)
    acwr = fnum(summary.get("acwr"), 1)
    hard = int(fnum(run_types.get("recent_28_hard_count"), 0))
    fade_val = fade.get("recent_mean_efficiency_change_pct")
    if long_km < 14:
        out.append({"rank": 1, "area": "Long-run durability", "status": "weak point", "message": f"Longest recent run is {clean(long_km,1)} km, so longer-race readiness is likely the main limiter.", "suggestion": "Build long-run exposure gradually before trusting longer-distance race predictions."})
    elif long_km < 20:
        out.append({"rank": 1, "area": "Durability", "status": "watch", "message": f"Longest recent run is {clean(long_km,1)} km: solid for shorter races, but still a limiter for marathon/ultra confidence.", "suggestion": "Keep extending long runs carefully while protecting easy days."})
    if tsb < -15 or acwr > 1.4:
        out.append({"rank": len(out)+1, "area": "Load management", "status": "caution", "message": f"Load signals suggest caution: TSB {clean(tsb,1)}, ACWR {clean(acwr,2)}.", "suggestion": "Prioritise consolidation and easy running over adding another hard session."})
    if finite(fade_val) and float(fade_val) < -5:
        out.append({"rank": len(out)+1, "area": "Steady-run fade", "status": "weak point", "message": f"Recent steady-run fade averages {clean(fade_val,1)}%, suggesting durability/fatigue may be limiting longer efforts.", "suggestion": "Use easy endurance runs and fuelling/hydration practice before adding much intensity."})
    if hard >= 4:
        out.append({"rank": len(out)+1, "area": "Hard/easy balance", "status": "watch", "message": f"There are {hard} hard-ish classified runs in the latest 28 classified runs.", "suggestion": "Make sure easy volume is not drifting into moderate effort too often."})
    if not out:
        out.append({"rank": 1, "area": "Consistency", "status": "default priority", "message": "No single weak point is dominant from the current public-safe metrics.", "suggestion": "Keep building consistently and reassess after more comparable data accumulates."})
    for i, p in enumerate(out[:5], 1):
        p["rank"] = i
    return {"generated_at_utc": now_iso(), "method": "Rule-based priorities from public-safe load, run-type, efficiency, matched-route and steady-run fade summaries.", "items": out[:5]}


def update_history(pred: dict[str, Any]) -> dict[str, Any]:
    hist = read_json(HISTORY, {"items": []}) or {"items": []}
    items = [x for x in (hist.get("items") or []) if x.get("date") != pred["date"]]
    for p in pred.get("items") or []:
        f = p.get("fitness_estimate") or {}
        items.append({"date": pred["date"], "race": p.get("race"), "fast_time_sec": f.get("fast_time_sec"), "slow_time_sec": f.get("slow_time_sec"), "fast_time": f.get("fast_time"), "slow_time": f.get("slow_time"), "readiness": (p.get("readiness") or {}).get("verdict"), "confidence": p.get("confidence")})
    hist = {"generated_at_utc": now_iso(), "method": "Daily snapshots of derived race-fitness estimates and readiness verdicts. Public-safe; no GPS or activity IDs.", "items": sorted(items, key=lambda x: (x.get("date", ""), x.get("race", "")))}
    write_json(HISTORY, hist)
    return hist


def main() -> int:
    cfg = get_config()
    summary = read_json(DATA / "summary.json", {}) or {}
    acts = read_json(DATA / "activities_recent.json", []) or []
    threshold = read_json(DATA / "threshold_history.json", {"items": []}) or {"items": []}
    fade = read_json(DATA / "steady_fade_verdict.json", {}) or {}
    eff = read_json(DATA / "efficiency_trends.json", {}) or {}
    matched = read_json(DATA / "matched_route_verdicts.json", {}) or {}
    run_types = read_json(DATA / "run_types.json", {}) or {}

    th = latest_threshold(threshold)
    th_fit = threshold_estimates(th)
    pred_items = []
    for race, dist, full_name in RACES:
        obs = observed_equivalents(acts, dist)
        fit = blended_estimate(race, dist, th_fit.get(race) if th_fit else None, obs)
        ready = readiness_for(race, dist, acts, summary, cfg)
        conf = "low"
        if fit and ready["verdict"] in {"ready", "mostly ready"}: conf = "medium"
        if fit and ready["verdict"] == "ready" and race in {"5K", "10K"}: conf = "medium-high"
        trend = trend_from_three_months(race, dist, fit, acts)
        focus = training_focus(race, ready, fade, eff)
        pred_items.append({"race": race, "full_name": full_name, "distance_km": dist, "fitness_estimate": fit, "threshold_estimate": th_fit.get(race) if th_fit else None, "observed_equivalents": obs[:5], "readiness": ready, "confidence": conf, "trend": trend, "training_focus": focus, "interpretation": "Fitness estimate blends threshold proxy and recent observed activity equivalents; trend compares current estimate with a roughly three-month-old performance window; readiness is separate."})

    predictions = {"generated_at_utc": now_iso(), "date": today(), "method": "Transparent heuristic. Race order is 5K, 10K, 1/2M, marathon, 50K, 100K. Fitness estimates blend threshold pace proxy with observed activity equivalents. Trend compares current performance with activity-derived equivalents from roughly three months ago. Readiness is separately gated by longest recent run and 28-day volume.", "threshold_anchor": th, "items": pred_items}
    priorities = build_training_priorities(summary, run_types, eff, fade, matched, acts)
    hist = update_history(predictions)
    write_json(DATA / "training_priorities.json", priorities)
    write_json(DATA / "race_predictions.json", predictions)
    insights = read_json(DATA / "insights.json", {}) or {}
    insights.update({"training_priorities": priorities, "race_predictions": predictions, "race_predictions_history": hist, "generated_at_utc": now_iso()})
    write_json(DATA / "insights.json", insights)
    print("[race-readiness] wrote ordered race predictions with 3-month performance trends")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
