#!/usr/bin/env python3
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs'/'data'
CONFIG=ROOT/'config'/'runmetrics_config.json'
HISTORY=DATA/'race_predictions_history.json'
DISTANCES={'5K':5.0,'10K':10.0,'Half marathon':21.0975,'Marathon':42.195}
DEFAULT_READINESS={'5K':{'min_recent_long_run_km':5,'min_28d_distance_km':20},'10K':{'min_recent_long_run_km':9,'min_28d_distance_km':35},'Half marathon':{'min_recent_long_run_km':16,'min_28d_distance_km':70},'Marathon':{'min_recent_long_run_km':28,'min_28d_distance_km':150}}
PACE_FACTORS={'5K':(0.90,0.95),'10K':(0.95,1.00),'Half marathon':(1.03,1.09),'Marathon':(1.13,1.24)}

def now(): return datetime.now(timezone.utc).isoformat()
def today(): return datetime.now(timezone.utc).date().isoformat()
def read_json(p:Path, default:Any):
    if not p.exists(): return default
    try:
        with p.open('r',encoding='utf-8') as f: return json.load(f)
    except Exception: return default
def write_json(p:Path,obj:Any):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w',encoding='utf-8') as f: json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')
def finite(x):
    try: return math.isfinite(float(x))
    except Exception: return False
def fnum(x,default=0.0): return float(x) if finite(x) else default
def clean(x,nd=1): return round(float(x),nd) if finite(x) else None
def hms(seconds):
    if not finite(seconds): return None
    s=int(round(float(seconds))); h=s//3600; m=(s%3600)//60; sec=s%60
    return f'{h}:{m:02d}:{sec:02d}' if h else f'{m}:{sec:02d}'
def latest_threshold(th):
    if th.get('latest'): return th['latest']
    items=th.get('items') or []
    return items[-1] if items else None
def longest(acts): return max([fnum(a.get('distance_km')) for a in acts] or [0.0])
def count_over(acts,km): return sum(1 for a in acts if fnum(a.get('distance_km'))>=km)
def get_config():
    cfg=read_json(CONFIG,{}) or {}
    rr=cfg.setdefault('race_readiness',{})
    for race,vals in DEFAULT_READINESS.items():
        rr.setdefault(race, vals.copy())
        for k,v in vals.items(): rr[race].setdefault(k,v)
    write_json(CONFIG,cfg)
    return cfg

def priorities(summary, run_types, eff, fade, matched_v, acts):
    out=[]; long_km=longest(acts); tsb=fnum(summary.get('tsb')); acwr=fnum(summary.get('acwr'),1); hard=int(fnum(run_types.get('recent_28_hard_count')))
    fade_val=fade.get('recent_mean_efficiency_change_pct'); eff_verdict=eff.get('verdict'); best=(matched_v.get('best_signal') or {}) if isinstance(matched_v,dict) else {}
    if long_km<14:
        out.append({'rank':1,'area':'Long-run durability','status':'weak point','message':f'Longest recent run is {clean(long_km,1)} km, so longer-race readiness is likely the main limiter.','suggestion':'Build long-run exposure gradually before trusting longer-distance race predictions.'})
    elif long_km<20:
        out.append({'rank':1,'area':'Durability','status':'watch','message':f'Longest recent run is {clean(long_km,1)} km: solid for shorter races, but still a limiter for marathon-specific confidence.','suggestion':'Keep extending long runs carefully while protecting easy days.'})
    if tsb < -15 or acwr > 1.4:
        out.append({'rank':len(out)+1,'area':'Load management','status':'caution','message':f'Load signals suggest caution: TSB {clean(tsb,1)}, ACWR {clean(acwr,2)}.','suggestion':'Prioritise consolidation and easy running over adding another hard session.'})
    if finite(fade_val) and float(fade_val)<-5:
        out.append({'rank':len(out)+1,'area':'Steady-run fade','status':'weak point','message':f'Recent steady-run fade averages {clean(fade_val,1)}%, suggesting durability/fatigue may be limiting longer efforts.','suggestion':'Use easy endurance runs and fuelling/hydration practice before adding much intensity.'})
    if eff_verdict in {'worsening','not enough data'}:
        out.append({'rank':len(out)+1,'area':'Easy-run efficiency','status':eff_verdict,'message':'Easy/steady speed per heartbeat is not clearly improving yet.' if eff_verdict=='worsening' else 'There is not enough clean easy/steady efficiency data yet.','suggestion':'Keep easy runs genuinely easy and collect more comparable HR data.'})
    elif eff_verdict=='improving':
        out.append({'rank':len(out)+1,'area':'Aerobic efficiency','status':'strength','message':'Easy/steady speed per heartbeat appears to be improving.','suggestion':'Maintain consistency; avoid over-testing this by turning easy runs into workouts.'})
    if hard>=4:
        out.append({'rank':len(out)+1,'area':'Hard/easy balance','status':'watch','message':f'There are {hard} hard-ish classified runs in the latest 28 classified runs.','suggestion':'Make sure easy volume is not drifting into moderate effort too often.'})
    if best.get('efficiency_change_pct') is not None:
        out.append({'rank':len(out)+1,'area':'Matched-route efficiency','status':'signal','message':f"Best matched-route signal is {best.get('efficiency_change_pct')}% speed per heartbeat.",'suggestion':'Use this as route-specific evidence, but keep broader easy-efficiency and durability signals in view.'})
    if not out:
        out.append({'rank':1,'area':'Consistency','status':'default priority','message':f"Recent load is {clean(summary.get('last_7d_distance_km'),1)} km in 7 days and {clean(summary.get('last_28d_distance_km'),1)} km in 28 days.",'suggestion':'Keep building consistently; no single weak point is dominant from the current public-safe metrics.'})
    for i,p in enumerate(out[:5],1): p['rank']=i
    return {'generated_at_utc':now(),'method':'Rule-based priorities from public-safe load, run-type, efficiency, matched-route and steady-run fade summaries.','items':out[:5]}

def fitness_estimates(th):
    if not th or not finite(th.get('threshold_pace_proxy_min_per_km')): return None
    tp=float(th['threshold_pace_proxy_min_per_km']); out={}
    for race,dist in DISTANCES.items():
        lo,hi=PACE_FACTORS[race]; fp=tp*lo; sp=tp*hi; fs=fp*60*dist; ss=sp*60*dist
        out[race]={'distance_km':dist,'fast_time_sec':clean(fs,0),'slow_time_sec':clean(ss,0),'fast_time':hms(fs),'slow_time':hms(ss),'pace_range_min_per_km':[clean(fp,2),clean(sp,2)]}
    return out

def readiness(race, acts, summary, cfg):
    rules=cfg['race_readiness'][race]; dist=DISTANCES[race]; long_km=longest(acts); d28=fnum(summary.get('last_28d_distance_km'))
    min_long=float(rules['min_recent_long_run_km']); min28=float(rules['min_28d_distance_km'])
    lr=long_km/min_long if min_long else 1; vr=d28/min28 if min28 else 1
    if lr>=1 and vr>=1: verdict='ready'; limiter='No obvious distance-specific limiter from current public-safe data.'
    elif lr>=0.8 and vr>=0.75: verdict='mostly ready'; limiter='Close to the distance-specific guardrails, but confidence would improve with more specific volume.'
    elif lr>=0.6 or vr>=0.6: verdict='plausible but durability-limited'; limiter='Fitness may exist, but recent long-run or 28-day volume is below the configured readiness guardrail.'
    else: verdict='not distance-ready'; limiter='Current data does not show enough distance-specific preparation; you probably should not trust the fitness estimate for this distance yet.'
    return {'verdict':verdict,'limiter':limiter,'longest_recent_run_km':clean(long_km,1),'last_28d_distance_km':clean(d28,1),'required_long_run_km':min_long,'required_28d_distance_km':min28,'runs_over_65pct_distance':count_over(acts,dist*0.65)}

def race_predictions(summary, acts, threshold, cfg):
    th=latest_threshold(threshold); fit=fitness_estimates(th); items=[]
    for race,dist in DISTANCES.items():
        ready=readiness(race,acts,summary,cfg); f=fit.get(race) if fit else None; conf='low'
        if f and ready['verdict'] in {'ready','mostly ready'}: conf='medium'
        if f and ready['verdict']=='ready' and race in {'5K','10K'}: conf='medium-high'
        if race=='Marathon' and ready['verdict']!='ready': conf='low'
        items.append({'race':race,'distance_km':dist,'fitness_estimate':f,'readiness':ready,'confidence':conf,'interpretation':'Fitness estimate is pace-derived; readiness checks whether recent distance-specific preparation supports actually racing that far.'})
    return {'generated_at_utc':now(),'date':today(),'method':'Transparent heuristic. Fitness estimates are anchored to threshold pace proxy. Readiness is separately gated by longest recent run and 28-day volume. This is not a guarantee of race performance.','threshold_anchor':th,'items':items}

def update_history(pred):
    hist=read_json(HISTORY,{'items':[]}) or {'items':[]}; items=[x for x in (hist.get('items') or []) if x.get('date')!=pred['date']]
    for p in pred.get('items') or []:
        f=p.get('fitness_estimate') or {}
        items.append({'date':pred['date'],'race':p.get('race'),'fast_time_sec':f.get('fast_time_sec'),'slow_time_sec':f.get('slow_time_sec'),'readiness':(p.get('readiness') or {}).get('verdict'),'confidence':p.get('confidence')})
    hist={'generated_at_utc':now(),'method':'Daily snapshots of derived race-fitness estimates and readiness verdicts. Public-safe; no GPS or activity IDs.','items':sorted(items,key=lambda x:(x.get('date',''),x.get('race','')))}
    write_json(HISTORY,hist); return hist

def main():
    cfg=get_config(); summary=read_json(DATA/'summary.json',{}) or {}; acts=read_json(DATA/'activities_recent.json',[]) or []
    threshold=read_json(DATA/'threshold_history.json',{'items':[]}) or {'items':[]}; fade=read_json(DATA/'steady_fade_verdict.json',{}) or {}; eff=read_json(DATA/'efficiency_trends.json',{}) or {}; matched=read_json(DATA/'matched_route_verdicts.json',{}) or {}; rt=read_json(DATA/'run_types.json',{}) or {}
    pr=priorities(summary,rt,eff,fade,matched,acts); pred=race_predictions(summary,acts,threshold,cfg); hist=update_history(pred)
    write_json(DATA/'training_priorities.json',pr); write_json(DATA/'race_predictions.json',pred)
    insights=read_json(DATA/'insights.json',{}) or {}; insights.update({'training_priorities':pr,'race_predictions':pred,'race_predictions_history':hist,'generated_at_utc':now()}); write_json(DATA/'insights.json',insights)
    print('[race-readiness] wrote training_priorities, race_predictions, race_predictions_history')
if __name__=='__main__': main()
