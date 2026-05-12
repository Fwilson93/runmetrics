async function rrLoad(path, fallback){try{const r=await fetch(path,{cache:'no-store'});if(!r.ok)return fallback;return await r.json();}catch{return fallback;}}
function rrPanel(id,html){const el=document.getElementById(id);if(el)el.innerHTML=html;}
function rrCard(cls,title,body,foot){return `<div class="mini-card ${cls||''}"><div class="mini-card-rank">${title}</div>${body}${foot?`<p class="small">${foot}</p>`:''}</div>`;}
function rrPriorities(data){const items=data.items||[];rrPanel('trainingPrioritiesPanel',items.map(p=>rrCard('',`Priority ${p.rank}: ${p.area}`,`<h3>${p.status}</h3><p>${p.message}</p>`,p.suggestion)).join('')||'<p class="small">No priorities yet.</p>');}
function rrTrendBadge(t){if(!t)return ''; const cls=(t.label||'').replaceAll(' ','-'); return `<p><strong>Trend:</strong> <span class="race-trend ${cls}">${t.label||'—'}</span> — ${t.message||''}</p>`;}
function rrPredictions(data){
  const items=data.items||[];
  rrPanel('racePredictionsPanel',items.map(p=>{
    const fit=p.fitness_estimate; const ready=p.readiness||{}; const focus=p.training_focus||{};
    const time=fit?`${fit.fast_time} – ${fit.slow_time}`:'not enough pace data';
    const source=fit&&fit.sources?`Sources: ${fit.sources.join(', ').replaceAll('_',' ')}`:'';
    const obs=fit&&fit.best_observed_equivalent?`Best observed equivalent: ${fit.best_observed_equivalent.estimated_time} from ${fit.best_observed_equivalent.source_distance_km} km on ${fit.best_observed_equivalent.date}.`:'';
    return rrCard('race-card',p.race,
      `<h3>${time}</h3>
       <p><strong>Readiness:</strong> ${ready.verdict||'—'}</p>
       <p><strong>Confidence:</strong> ${p.confidence||'—'}</p>
       ${rrTrendBadge(p.trend)}
       <p><strong>Training focus:</strong> ${focus.primary||'—'}</p>
       <p class="small">${focus.training_emphasis||''}</p>
       <p class="small">${source}</p>
       <p class="small">${obs}</p>`,
      focus.rationale || ready.limiter || p.interpretation);
  }).join('')||'<p class="small">No race predictions yet.</p>');
}
function rrHistory(hist){
  const items=hist.items||[]; const latestDates=[...new Set(items.map(x=>x.date))].slice(-8); const recent=items.filter(x=>latestDates.includes(x.date));
  if(!recent.length){rrPanel('racePredictionHistoryPanel','<p class="small">No prediction history yet.</p>');return;}
  const rows=recent.map(x=>`<tr><td>${x.date}</td><td>${x.race}</td><td>${x.fast_time&&x.slow_time?`${x.fast_time} – ${x.slow_time}`:'—'}</td><td>${x.readiness||'—'}</td><td>${x.confidence||'—'}</td></tr>`).join('');
  rrPanel('racePredictionHistoryPanel',`<div class="table-wrap"><table><thead><tr><th>Date</th><th>Race</th><th>Estimate</th><th>Readiness</th><th>Confidence</th></tr></thead><tbody>${rows}</tbody></table></div><p class="small">History is updated once per update day; estimates are heuristic and readiness-gated.</p>`);
}
async function rrMain(){const [p,r,h]=await Promise.all([rrLoad('./data/training_priorities.json',{}),rrLoad('./data/race_predictions.json',{}),rrLoad('./data/race_predictions_history.json',{})]);rrPriorities(p);rrPredictions(r);rrHistory(h);}rrMain();
