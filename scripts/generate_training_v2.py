#!/usr/bin/env python3
from __future__ import annotations
import json, math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
DATA.mkdir(parents=True, exist_ok=True)

def now(): return datetime.now(timezone.utc).isoformat()
def read_json(p: Path, default=None):
    if not p.exists(): return default
    with p.open("r", encoding="utf-8") as f: return json.load(f)
def write_json(p: Path, obj: Any):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False); f.write("\n")
def finite(x):
    try: return math.isfinite(float(x))
    except Exception: return False
def fnum(x, default=0.0): return float(x) if finite(x) else default
def clean(x, nd=2): return round(float(x), nd) if finite(x) else None
def pct(new, old):
    return ((float(new)-float(old))/float(old))*100 if finite(new) and finite(old) and float(old) != 0 else None
def mean(vals):
    xs=[float(v) for v in vals if finite(v)]
    return float(np.mean(xs)) if xs else None
def last(items,n): return items[-n:] if len(items)>n else items

def latest_thr(th):
    if th.get("latest"): return th["latest"]
    items=th.get("items") or []
    return items[-1] if items else None

def classify(r, th):
    dist=fnum(r.get("distance_km")); dur=fnum(r.get("moving_time_min")); elev=fnum(r.get("elev_gain_m")); hr=r.get("avg_hr")
    epk=elev/dist if dist>0 else 0
    thr=fnum(th.get("threshold_hr_proxy"),0) if th else 0
    hrr=float(hr)/thr if finite(hr) and thr>0 else None
    labels=[]
    if epk>=35: labels.append("hilly")
    if (r.get("sport_type") or "").lower().startswith("trail"): labels.append("trail")
    if dist>=16 or dur>=95: typ="long"
    elif hrr is not None and hrr>=0.98: typ="hard / race-like"
    elif hrr is not None and hrr>=0.92: typ="threshold-ish"
    elif hrr is not None and hrr>=0.84: typ="steady"
    elif dur<=35 and (hrr is None or hrr<0.78): typ="recovery"
    else: typ="easy"
    if typ not in labels: labels.insert(0, typ)
    speed=dist/(dur/60) if dist>0 and dur>0 else None
    eff=speed/float(hr) if speed is not None and finite(hr) and float(hr)>0 else None
    return {"date":r.get("date"),"type":typ,"labels":labels,"distance_km":clean(dist,2),"duration_min":clean(dur,1),"elev_gain_m":clean(elev,0),"elev_per_km":clean(epk,1),"avg_hr":clean(hr,1),"hr_ratio_to_threshold":clean(hrr,3),"pace_min_per_km":clean(r.get("pace_min_per_km"),2),"efficiency_kmh_per_bpm":clean(eff,4)}

def run_types(classified):
    counts=Counter(x["type"] for x in classified); total=sum(counts.values()) or 1
    recent=classified[-28:]; rc=Counter(x["type"] for x in recent); rtot=sum(rc.values()) or 1
    return {"generated_at_utc":now(),"method":"Public-safe deterministic run classification from distance, duration, elevation, HR relative to threshold proxy, and sport type. No activity IDs, names, routes or GPS are exported.","items":[{"type":k,"count":v,"pct":clean(100*v/total,1)} for k,v in sorted(counts.items(), key=lambda kv:(-kv[1],kv[0]))],"recent_28_run_items":[{"type":k,"count":v,"pct":clean(100*v/rtot,1)} for k,v in sorted(rc.items(), key=lambda kv:(-kv[1],kv[0]))],"recent_28_hard_count":sum(1 for x in recent if x["type"] in {"threshold-ish","hard / race-like"}),"recent_28_easy_or_long_count":sum(1 for x in recent if x["type"] in {"recovery","easy","long"}),"classified_runs":classified[-120:]}

def efficiency(classified):
    elig=[x for x in classified if x.get("type") in {"recovery","easy","steady"} and finite(x.get("efficiency_kmh_per_bpm")) and fnum(x.get("distance_km"))>=3 and fnum(x.get("elev_per_km"))<=35]
    items=[]
    for i,x in enumerate(elig):
        tr=elig[max(0,i-5):i+1]
        items.append({"date":x.get("date"),"efficiency_kmh_per_bpm":clean(x.get("efficiency_kmh_per_bpm"),4),"rolling_efficiency_kmh_per_bpm":clean(mean([r.get("efficiency_kmh_per_bpm") for r in tr]),4),"rolling_pace_min_per_km":clean(mean([r.get("pace_min_per_km") for r in tr]),2),"rolling_avg_hr":clean(mean([r.get("avg_hr") for r in tr]),1),"type":x.get("type")})
    recent=items[-6:]; older=items[-12:-6]; delta=None; verdict="not enough data"
    if len(recent)>=3 and len(older)>=3:
        delta=pct(mean([x.get("rolling_efficiency_kmh_per_bpm") for x in recent]), mean([x.get("rolling_efficiency_kmh_per_bpm") for x in older]))
        if finite(delta): verdict="improving" if delta>=3 else "worsening" if delta<=-3 else "stable"
    return {"generated_at_utc":now(),"method":"Easy/steady efficiency = speed_kmh divided by average HR for non-hilly recovery/easy/steady runs. Higher means more speed per heartbeat.","verdict":verdict,"recent_vs_previous_efficiency_pct":clean(delta,1),"items":items[-80:]}

def fade_verdict(drift):
    vals=[x.get("efficiency_change_pct") for x in last(drift.get("items") or [],8) if finite(x.get("efficiency_change_pct"))]
    avg=mean(vals)
    if avg is None: label,msg="not enough data","Need more steady runs with HR and speed streams."
    elif avg>=-2: label,msg="held together well","Recent steady runs show little fade. Speed per heartbeat is holding up well."
    elif avg>=-5: label,msg="mild fade","Recent steady runs show mild fade. This is common, but worth watching."
    elif avg>=-8: label,msg="noticeable fade","Recent steady runs show noticeable fade. Fatigue, hills, heat, fuelling or sensor noise may be contributing."
    else: label,msg="strong fade","Recent steady runs show strong fade. Treat this as a recovery/consolidation warning unless terrain or HR noise explains it."
    return {"label":label,"recent_mean_efficiency_change_pct":clean(avg,1),"message":msg,"plain_english":"This checks whether you get less speed for the same heartbeat in the second half of steady runs. Closer to 0% is better; strongly negative means you faded."}

def matched_verdicts(matched):
    items=[]
    for r in matched.get("items") or []:
        eff=r.get("latest_vs_previous_median_efficiency_pct"); pace=r.get("latest_vs_previous_median_pace_pct"); hr=r.get("latest_vs_previous_median_hr_pct")
        if finite(eff):
            verdict="probably fitter" if float(eff)>=3 else "probably less efficient" if float(eff)<=-3 else "similar fitness signal"
            why="More speed per heartbeat than your previous median on this GPS-matched route." if float(eff)>=3 else "Less speed per heartbeat than your previous median on this GPS-matched route." if float(eff)<=-3 else "Efficiency is close to your previous median."
        else: verdict,why="insufficient HR data","Need HR data to distinguish fitness from simply pushing harder."
        items.append({"label":r.get("label"),"count":r.get("count"),"latest_date":r.get("latest_date"),"efficiency_change_pct":clean(eff,1),"pace_change_pct":clean(pace,1),"hr_change_pct":clean(hr,1),"verdict":verdict,"why":why})
    best=max([x for x in items if finite(x.get("efficiency_change_pct"))], key=lambda x:float(x["efficiency_change_pct"]), default=None)
    return {"generated_at_utc":now(),"method":"Matched-route verdicts are efficiency-led: faster alone is not enough; the question is whether speed per heartbeat improved.","best_signal":best,"items":items}

def block_review(daily, threshold, drift, mv):
    rows=[]
    for days in [28,56,84]:
        chunk=last(daily,days); prev=daily[-2*days:-days] if len(daily)>=2*days else []
        dist=sum(fnum(x.get("distance_km")) for x in chunk); load=sum(fnum(x.get("load_trimp")) for x in chunk); elev=sum(fnum(x.get("elev_gain_m")) for x in chunk); active=sum(1 for x in chunk if fnum(x.get("distance_km"))>0)
        pdist=sum(fnum(x.get("distance_km")) for x in prev) if prev else None; dd=pct(dist,pdist)
        parts=[]
        if finite(dd): parts.append("volume is up sharply" if dd>20 else "volume is down sharply" if dd<-20 else "volume is broadly stable")
        th=latest_thr(threshold)
        if th: parts.append(f"threshold proxy is {th.get('threshold_hr_proxy')} bpm")
        fv=fade_verdict(drift)
        if fv.get("label")!="not enough data": parts.append(f"steady-run fade is {fv.get('label')}")
        best=mv.get("best_signal")
        if best: parts.append(f"best matched-route signal is {best.get('efficiency_change_pct')}%")
        if not parts: parts.append("not enough data for a robust narrative yet")
        rows.append({"label":f"Last {days//7} weeks","days":days,"distance_km":clean(dist,1),"km_per_week":clean(dist/(days/7),1),"load":clean(load,0),"elev_gain_m":clean(elev,0),"active_days":active,"distance_vs_previous_block_pct":clean(dd,1),"narrative":"; ".join(parts)+"."})
    return {"generated_at_utc":now(),"items":rows}

def fun_stats(daily, weekly, classified, mv, eff):
    stats=[]
    if daily: stats.append({"label":"Longest public-window day","value":f"{clean(max(daily,key=lambda x:fnum(x.get('distance_km'))).get('distance_km'),1)} km"})
    if weekly: stats.append({"label":"Biggest public-window week","value":f"{clean(max(weekly,key=lambda x:fnum(x.get('distance_km'))).get('distance_km'),1)} km"})
    best=mv.get("best_signal")
    if best: stats.append({"label":"Best matched-route efficiency signal","value":f"{best.get('efficiency_change_pct')}%","context":best.get("label")})
    ei=eff.get("items") or []
    if ei:
        be=max(ei,key=lambda x:fnum(x.get("efficiency_kmh_per_bpm")))
        stats.append({"label":"Best easy/steady efficiency","value":clean(be.get("efficiency_kmh_per_bpm"),4),"context":be.get("date")})
    stats.append({"label":"Hard-ish runs in latest 28 classified runs","value":sum(1 for x in last(classified,28) if x.get("type") in {"threshold-ish","hard / race-like"})})
    return {"generated_at_utc":now(),"items":stats}

def main():
    recent=read_json(DATA/"activities_recent.json",[]) or []; daily=read_json(DATA/"daily_metrics.json",[]) or []; weekly=read_json(DATA/"weekly_metrics.json",[]) or []
    threshold=read_json(DATA/"threshold_history.json",{"items":[]}) or {"items":[]}; drift=read_json(DATA/"drift_summary.json",{"items":[]}) or {"items":[]}; matched=read_json(DATA/"matched_runs.json",{"items":[]}) or {"items":[]}; insights=read_json(DATA/"insights.json",{}) or {}
    classified=[classify(r,latest_thr(threshold)) for r in recent]
    rt=run_types(classified); eff=efficiency(classified); fade=fade_verdict(drift); mv=matched_verdicts(matched); br=block_review(daily,threshold,drift,mv); fs=fun_stats(daily,weekly,classified,mv,eff)
    for name,obj in [("run_types",rt),("efficiency_trends",eff),("matched_route_verdicts",mv),("steady_fade_verdict",fade),("block_review",br),("fun_stats_v2",fs)]: write_json(DATA/f"{name}.json",obj)
    insights.update({"run_type_summary":rt,"easy_run_efficiency":eff,"matched_route_verdicts":mv,"steady_fade_verdict":fade,"block_review":br,"fun_stats_v2":fs,"generated_at_utc":now()})
    write_json(DATA/"insights.json",insights)
    print("[training-v2] wrote run classification, efficiency trends, matched-route verdicts, fade verdict, block review, fun stats v2")
if __name__=="__main__": main()
