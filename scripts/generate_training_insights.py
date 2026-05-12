#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = DOCS / "data"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def clean(x: Any, nd: int = 1) -> float | None:
    if not finite(x):
        return None
    return round(float(x), nd)


def pace_label(v: Any) -> str:
    if not finite(v):
        return "—"
    x = float(v)
    m = int(x)
    s = int(round((x - m) * 60))
    return f"{m}:{s:02d}/km"


def last(items: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    return items[-n:] if len(items) > n else items


def sum_field(items: list[dict[str, Any]], field: str) -> float:
    return sum(fnum(x.get(field), 0.0) for x in items)


def mean_field(items: list[dict[str, Any]], field: str) -> float | None:
    vals = [fnum(x.get(field)) for x in items if finite(x.get(field))]
    return sum(vals) / len(vals) if vals else None


def build_suggested_next_run(summary, threshold, drift, matched):
    tsb = fnum(summary.get("tsb"), 0)
    acwr = fnum(summary.get("acwr"), 1)
    d7 = fnum(summary.get("last_7d_distance_km"), 0)
    days = int(fnum(summary.get("last_7d_activity_days"), 0))

    drift_items = drift.get("items") or []
    drift_recent = mean_field(last(drift_items, 5), "efficiency_change_pct")

    latest_thr = threshold.get("latest") or {}
    thr_conf = latest_thr.get("confidence") or "unknown"

    options = []

    caution_flags = []
    if tsb < -20:
        caution_flags.append("very negative TSB")
    if acwr > 1.5:
        caution_flags.append("high acute:chronic load")
    if drift_recent is not None and drift_recent < -7:
        caution_flags.append("recent steady-run fade")
    if days >= 6:
        caution_flags.append("many running days this week")

    if caution_flags:
        options.append({
            "rank": 1,
            "title": "Recovery / very easy run",
            "session": "Rest, mobility, or 30–45 min very easy.",
            "why": "Chosen because: " + ", ".join(caution_flags) + ".",
            "intensity": "Keep it conversational. Avoid turning this into a moderate run.",
        })
        options.append({
            "rank": 2,
            "title": "Easy aerobic maintenance",
            "session": "40–55 min easy if legs feel normal.",
            "why": "This keeps frequency without adding much extra stress.",
            "intensity": "Stay below the lower end of the threshold-derived Z2 band if possible.",
        })
        options.append({
            "rank": 3,
            "title": "Defer quality",
            "session": "Move threshold/interval work to a fresher day.",
            "why": "The dashboard signals suggest consolidation is more useful than forcing intensity.",
            "intensity": "No hard finish.",
        })
    elif tsb >= -8 and 0.8 <= acwr <= 1.35 and thr_conf in {"medium", "high"}:
        options.append({
            "rank": 1,
            "title": "Controlled quality session",
            "session": "Example: 3 × 8 min controlled threshold effort with easy jog recoveries.",
            "why": "Load is not flashing red, and the threshold proxy has enough confidence to guide effort.",
            "intensity": "Aim around threshold proxy effort, not a race effort.",
        })
        options.append({
            "rank": 2,
            "title": "Aerobic endurance run",
            "session": "50–70 min easy to steady.",
            "why": "Good default if legs feel flat or life stress is high.",
            "intensity": "Smooth and boring is the point.",
        })
        options.append({
            "rank": 3,
            "title": "Short hills / strides",
            "session": "Easy run plus 6–8 short relaxed strides or hill sprints.",
            "why": "Adds neuromuscular stimulus without making the whole run hard.",
            "intensity": "Full recovery between efforts.",
        })
    else:
        options.append({
            "rank": 1,
            "title": "Easy aerobic run",
            "session": "45–60 min easy.",
            "why": "Current signals are mixed rather than clearly fresh or clearly overloaded.",
            "intensity": "Keep it comfortable; finish feeling like you could do more.",
        })
        options.append({
            "rank": 2,
            "title": "Aerobic durability run",
            "session": "60–80 min easy if legs are good.",
            "why": "Useful for marathon/ultra development without needing high intensity.",
            "intensity": "Watch for steady-run fade rather than chasing pace.",
        })
        options.append({
            "rank": 3,
            "title": "Light quality touch",
            "session": "20–30 min easy plus 4–6 relaxed strides.",
            "why": "A small stimulus if you want some sharpness without much load.",
            "intensity": "Relaxed, not maximal.",
        })

    return {
        "title": options[0]["title"] if options else "Easy aerobic run",
        "options": options,
        "inputs": {
            "tsb": clean(tsb, 1),
            "acwr": clean(acwr, 2),
            "last_7d_distance_km": clean(d7, 1),
            "last_7d_activity_days": days,
            "recent_drift_mean_pct": clean(drift_recent, 1),
            "threshold_confidence": thr_conf,
        },
    }


def build_load_caution(summary, drift):
    tsb = fnum(summary.get("tsb"), 0)
    acwr = fnum(summary.get("acwr"), 1)
    d7 = fnum(summary.get("last_7d_distance_km"), 0)
    d28 = fnum(summary.get("last_28d_distance_km"), 0)
    days = int(fnum(summary.get("last_7d_activity_days"), 0))
    drift_recent = mean_field(last(drift.get("items") or [], 5), "efficiency_change_pct")

    score = 0
    reasons = []

    if tsb < -20:
        score += 3
        reasons.append("TSB is very negative")
    elif tsb < -10:
        score += 2
        reasons.append("TSB is moderately negative")

    if acwr > 1.5:
        score += 3
        reasons.append("ACWR is high")
    elif acwr > 1.25:
        score += 1
        reasons.append("ACWR is elevated")

    if d28 > 0 and d7 / (d28 / 4.0) > 1.25:
        score += 1
        reasons.append("this week is above the recent weekly baseline")

    if days >= 6:
        score += 1
        reasons.append("many running days in the last week")

    if drift_recent is not None and drift_recent < -7:
        score += 2
        reasons.append("recent steady-run fade is noticeable")
    elif drift_recent is not None and drift_recent < -3:
        score += 1
        reasons.append("recent steady-run fade is mild")

    if score >= 5:
        level = "high"
        message = "High caution: the next training choice should reduce stress rather than add more."
    elif score >= 3:
        level = "moderate"
        message = "Moderate caution: training is probably productive, but easy days need to stay easy."
    else:
        level = "low"
        message = "Low caution: nothing obvious is flashing red in the current dashboard signals."

    return {
        "level": level,
        "score": score,
        "message": message,
        "reasons": reasons or ["No major load warning from current public-safe metrics."],
    }


def build_weekly_digest(summary, weekly, threshold, drift, matched):
    bullets = []

    if weekly:
        last_week = weekly[-1]
        if finite(last_week.get("distance_km")):
            bullets.append(f"Latest weekly distance is {clean(last_week.get('distance_km'), 1)} km.")
        if finite(last_week.get("load_trimp")):
            bullets.append(f"Latest weekly load is {clean(last_week.get('load_trimp'), 0)} TRIMP-derived units.")

    latest_thr = threshold.get("latest")
    if latest_thr:
        bullets.append(
            f"Threshold proxy is {latest_thr.get('threshold_hr_proxy')} bpm "
            f"with {latest_thr.get('confidence')} confidence."
        )

    drift_items = drift.get("items") or []
    if drift_items:
        recent = mean_field(last(drift_items, 5), "efficiency_change_pct")
        if recent is not None:
            if recent < -7:
                label = "noticeable fade"
            elif recent < -3:
                label = "mild fade"
            else:
                label = "controlled fade"
            bullets.append(f"Recent steady-run fade averages {clean(recent, 1)}%, which looks like {label}.")

    groups = matched.get("items") or []
    if groups:
        best = groups[0]
        bullets.append(
            f"Matched-runs table has {len(groups)} public-safe groups; the largest/most recent group is {best.get('label')}."
        )

    if finite(summary.get("last_7d_distance_km")) and finite(summary.get("last_28d_distance_km")):
        bullets.append(
            f"Rolling context: {summary.get('last_7d_distance_km')} km in 7 days and "
            f"{summary.get('last_28d_distance_km')} km in 28 days."
        )

    return bullets


def build_durability(drift):
    items = drift.get("items") or []
    recent = last(items, 8)
    vals = [float(x.get("efficiency_change_pct")) for x in recent if finite(x.get("efficiency_change_pct"))]

    if not vals:
        return {
            "label": "not enough data",
            "score": None,
            "message": "Need more steady runs of at least 35 minutes with HR and speed streams.",
        }

    avg = sum(vals) / len(vals)

    # Less negative / positive is better here.
    if avg >= -2:
        label = "good"
        score = 85
        msg = "Recent steady efforts show little fade: speed per heartbeat is holding up well."
    elif avg >= -5:
        label = "fair"
        score = 65
        msg = "Recent steady efforts show some fade, but not enough to panic."
    elif avg >= -8:
        label = "watch"
        score = 45
        msg = "Recent steady efforts show noticeable fade. This often points towards fatigue, heat, hills, fuelling, or insufficient aerobic durability."
    else:
        label = "poor"
        score = 30
        msg = "Recent steady efforts show large fade. Treat this as a recovery/consolidation warning unless terrain or sensor issues explain it."

    return {
        "label": label,
        "score": score,
        "recent_mean_efficiency_change_pct": clean(avg, 1),
        "message": msg,
        "plain_english": (
            "This is the intuitive version of HR drift: if you get less speed for the same heartbeat "
            "in the second half of a steady run, the run is fading. Closer to 0% is better; strongly negative is worse."
        ),
    }


def build_training_blocks(daily):
    blocks = []
    for days in [28, 56, 84]:
        chunk = last(daily, days)
        if not chunk:
            continue
        dist = sum_field(chunk, "distance_km")
        load = sum_field(chunk, "load_trimp")
        elev = sum_field(chunk, "elev_gain_m")
        active = sum(1 for x in chunk if fnum(x.get("distance_km"), 0) > 0)
        blocks.append({
            "label": f"Last {days // 7} weeks",
            "days": days,
            "distance_km": clean(dist, 1),
            "load": clean(load, 0),
            "elev_gain_m": clean(elev, 0),
            "active_days": active,
            "mean_km_per_week": clean(dist / (days / 7.0), 1),
        })
    return blocks


def build_fun_stats(daily, weekly, recent, matched):
    stats = []

    if daily:
        best_day = max(daily, key=lambda x: fnum(x.get("distance_km"), 0))
        stats.append({
            "label": "Longest day in public data window",
            "value": f"{clean(best_day.get('distance_km'), 1)} km",
            "context": best_day.get("date"),
        })

        biggest_load = max(daily, key=lambda x: fnum(x.get("load_trimp"), 0))
        stats.append({
            "label": "Biggest load day",
            "value": f"{clean(biggest_load.get('load_trimp'), 0)} load",
            "context": biggest_load.get("date"),
        })

    if weekly:
        best_week = max(weekly, key=lambda x: fnum(x.get("distance_km"), 0))
        stats.append({
            "label": "Biggest week in public data window",
            "value": f"{clean(best_week.get('distance_km'), 1)} km",
            "context": best_week.get("date"),
        })

    pace_runs = [x for x in recent if finite(x.get("pace_min_per_km")) and finite(x.get("distance_km"))]
    if pace_runs:
        fastest = min(pace_runs, key=lambda x: fnum(x.get("pace_min_per_km"), 99))
        stats.append({
            "label": "Fastest recent average pace",
            "value": pace_label(fastest.get("pace_min_per_km")),
            "context": f"{fastest.get('distance_km')} km on {fastest.get('date')}",
        })

    groups = matched.get("items") or []
    if groups:
        g = groups[0]
        stats.append({
            "label": "Most repeated matched-run group",
            "value": f"{g.get('count')} similar efforts",
            "context": f"{g.get('typical_distance_km')} km / {g.get('typical_elev_gain_m')} m",
        })

    return stats


def build_heatmap(daily):
    out = []
    for x in last(daily, 180):
        km = fnum(x.get("distance_km"), 0)
        load = fnum(x.get("load_trimp"), 0)
        if km <= 0:
            bucket = 0
        elif km < 5:
            bucket = 1
        elif km < 10:
            bucket = 2
        elif km < 16:
            bucket = 3
        else:
            bucket = 4
        out.append({
            "date": x.get("date"),
            "distance_km": clean(km, 1),
            "load": clean(load, 0),
            "bucket": bucket,
        })
    return out


def main() -> int:
    summary = read_json(DATA / "summary.json", {}) or {}
    daily = read_json(DATA / "daily_metrics.json", []) or []
    weekly = read_json(DATA / "weekly_metrics.json", []) or []
    recent = read_json(DATA / "activities_recent.json", []) or []
    threshold = read_json(DATA / "threshold_history.json", {"items": [], "latest": None}) or {"items": [], "latest": None}
    drift = read_json(DATA / "drift_summary.json", {"items": []}) or {"items": []}
    matched = read_json(DATA / "matched_runs.json", {"items": []}) or {"items": []}

    insights = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "privacy": {
            "public_site_policy": (
                "Public outputs intentionally avoid GPS coordinates, polylines, maps, activity IDs, activity names, "
                "route names, start/end coordinates, and exact route fingerprints. Matched runs use rounded distance/elevation only."
            ),
            "home_address_risk_control": (
                "No public field should be sufficient to reconstruct home location or habitual start/end points."
            ),
        },
        "suggested_next_run": build_suggested_next_run(summary, threshold, drift, matched),
        "load_caution": build_load_caution(summary, drift),
        "weekly_digest": build_weekly_digest(summary, weekly, threshold, drift, matched),
        "aerobic_durability": build_durability(drift),
        "training_blocks": build_training_blocks(daily),
        "fun_stats": build_fun_stats(daily, weekly, recent, matched),
        "heatmap": build_heatmap(daily),
    }

    write_json(DATA / "insights.json", insights)
    print("[insights] wrote docs/data/insights.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
