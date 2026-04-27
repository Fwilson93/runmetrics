const API = "https://runmetrics.onrender.com";
const apiEl = document.getElementById("api_url");
if(apiEl) apiEl.textContent = API;

function fmt(x, dp=1){
  if(x === null || x === undefined || Number.isNaN(Number(x))) return "";
  return Number(x).toFixed(dp);
}

async function fetchJSON(url){
  const r = await fetch(url);
  const t = await r.text();
  if(!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url} :: ${t.slice(0,200)}`);
  try { return JSON.parse(t); } catch { throw new Error(`Bad JSON from ${url} :: ${t.slice(0,200)}`); }
}

const DARK = {
  paper_bgcolor:"#0f1117",
  plot_bgcolor:"#0f1117",
  font:{color:"#e9eef6"},
  xaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
  yaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
  legend:{orientation:"h", font:{size:10}, y:-0.35},
  margin:{t:20,r:10,l:60,b:95},
};

const C = { ctl:"#6aa9ff", atl:"#ff6b6b", tsb:"#3ddc97" };

function nextDatesFrom(lastIsoDate, n){
  const base = new Date(lastIsoDate + "T00:00:00Z");
  const out = [];
  for(let i=1;i<=n;i++){
    const d = new Date(base.getTime() + i*24*3600*1000);
    out.push(d.toISOString().slice(0,10));
  }
  return out;
}

function intensityLabel(intensity){
  const pct = Math.round(intensity*100);
  if (pct <= 52) return "Easy jog";
  if (pct <= 62) return "Easy aerobic";
  if (pct <= 68) return "Aerobic (Z2)";
  if (pct <= 75) return "Steady";
  if (pct <= 83) return "Tempo";
  return "Hard";
}

function recBadge(rec){
  const c = rec==="good" ? "#3ddc97" : (rec==="caution" ? "#ffcc66" : "#ff6b6b");
  const t = rec==="good" ? "✅ sensible" : (rec==="caution" ? "⚠️ caution" : "⛔ risky");
  return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid ${c};color:${c}">${t}</span>`;
}

function arrowFor(v){ return v > 1 ? "↑" : (v < -1 ? "↓" : "↔"); }
function fatigueText(v){ return v > 1 ? "more tired" : (v < -1 ? "less tired" : "about the same"); }
function freshnessText(v){ return v > 1 ? "fresher" : (v < -1 ? "more tired" : "about the same"); }

function clampWorkout(dur, intensity){
  const safeDur = Math.max(5, Math.min(180, Number(dur)));
  const safeInt = Math.max(0.40, Math.min(0.95, Number(intensity)));
  return { dur: safeDur, intensity: safeInt };
}

/**
 * Stable recommendation (does NOT depend on sliders).
 * We keep this simple and science-honest:
 * - Use /api/recommendation if present; else fall back to a conservative default.
 */
let RECOMMENDED = null;
async function loadRecommendation(){
  try {
    const rec = await fetchJSON(`${API}/api/recommendation?days=7`);
    if(rec.status === "ok") return rec.best;
  } catch {}
  // fallback (no backend endpoint) — safe aerobic default
  return { label:"45 min Aerobic (Z2)", dur_min:45, intensity:0.65, delta_ctl:0, delta_atl:0, delta_tsb:0, recommendation:"good" };
}

function setCustomDefaultsAmbitious(rec){
  // Custom defaults: slightly more ambitious but sensible vs recommended
  const durEl = document.getElementById("dur");
  const intEl = document.getElementById("intensity_mode");
  if(!durEl || !intEl) return;

  let dur = rec.dur_min || 45;
  let intensity = rec.intensity || 0.65;

  // If recommended is aerobic -> add duration; if already intense -> add small intensity bump
  if (intensity <= 0.68){
    dur = Math.min(dur + 15, 90);
  } else {
    intensity = Math.min(intensity + 0.03, 0.80);
  }

  const c = clampWorkout(dur, intensity);
  durEl.value = String(Math.round(c.dur/5)*5);

  // intensity_mode is a <select> with fixed values; snap to nearest option
  const opts = Array.from(intEl.options).map(o => Number(o.value));
  const nearest = opts.reduce((best,v)=> (Math.abs(v-c.intensity) < Math.abs(best-c.intensity) ? v : best), opts[0]);
  intEl.value = nearest.toFixed(2);

  const lbl = document.getElementById("dur_lbl");
  if(lbl) lbl.textContent = durEl.value;
}

function computeRestDeltas(current){
  // Analytic one-step decay consistent with tau ATL=7, CTL=42.
  const ctl_tau = 42.0;
  const atl_tau = 7.0;
  const alpha_ctl = 1.0 - Math.exp(-1.0 / ctl_tau);
  const alpha_atl = 1.0 - Math.exp(-1.0 / atl_tau);

  const ctl_next = current.ctl * (1.0 - alpha_ctl);
  const atl_next = current.atl * (1.0 - alpha_atl);
  const tsb_next = ctl_next - atl_next;

  return {
    delta_ctl: ctl_next - current.ctl,
    delta_atl: atl_next - current.atl,
    delta_tsb: tsb_next - current.tsb,
    recommendation: (tsb_next > -15 ? "good" : "caution")
  };
}

function updateRecommendationExplanation(rec, histSeries, weekZones){
  const el = document.getElementById("recommendation_explain");
  if(!el || !rec || !histSeries.length) return;

  const last = histSeries[histSeries.length - 1];
  const tsb = last.tsb;

  let z3frac = null;
  if(weekZones){
    const order = ["Z1","Z2","Z3","Z4","Z5"];
    const mins = order.map(z => (weekZones[z]?.minutes ?? 0));
    const total = mins.reduce((a,b)=>a+b,0) || 1;
    z3frac = mins[2]/total;
  }

  const reasons = [];
  if(tsb < -10) reasons.push("your short‑term fatigue is elevated");
  if(z3frac !== null and z3frac > 0.25) reasons.push("recent training has been tempo‑heavy");
  if(!reasons.length) reasons.push("your current fitness–fatigue balance supports steady work");

  const tradeoff = (rec.intensity <= 0.68)
    ? "This prioritises aerobic efficiency and durability, but does not strongly stimulate high‑intensity (Z4–Z5) performance."
    : "This targets higher‑intensity adaptations, but adds fatigue and should be balanced with easier aerobic work.";

  el.innerHTML = `
    <strong>Recommended for tomorrow:</strong> ${Math.round(rec.dur_min)} min ${rec.label}.<br>
    Because ${reasons.join(" and ")}, this is a sensible choice today.<br>
    <em>Trade‑off:</em> ${tradeoff}
  `;
}

async function scenariosDynamic(dur_min, intensity){
  const w = clampWorkout(dur_min, intensity);
  return await fetchJSON(`${API}/api/scenarios_dynamic?days=7&dur_min=${w.dur}&intensity=${w.intensity}`);
}

async function renderScenarioTable(restRow, recRow, customRow){
  const rows = [
    {label:"Rest", dctl:restRow.delta_ctl, datl:restRow.delta_atl, dtsb:restRow.delta_tsb, rec:restRow.recommendation},
    {label:`Recommended (${Math.round(recRow.dur_min)} min ${intensityLabel(recRow.intensity)})`, dctl:recRow.delta_ctl, datl:recRow.delta_atl, dtsb:recRow.delta_tsb, rec:recRow.recommendation},
    {label:"Custom", dctl:customRow.delta_ctl, datl:customRow.delta_atl, dtsb:customRow.delta_tsb, rec:customRow.recommendation},
  ];

  const tableRows = rows.map(r => `
    <tr>
      <td><strong>${r.label}</strong></td>
      <td class="num">${arrowFor(r.dctl)} <span class="muted">${fmt(r.dctl,1)}</span></td>
      <td>${fatigueText(r.datl)} <span class="muted">(${fmt(r.datl,1)})</span></td>
      <td>${freshnessText(r.dtsb)} <span class="muted">(${fmt(r.dtsb,1)})</span></td>
      <td>${recBadge(r.rec)}</td>
    </tr>
  `).join("");

  document.getElementById("scenario_table").innerHTML = `
    <div class="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Option</th>
            <th class="num">Fitness change</th>
            <th>Fatigue change</th>
            <th>Freshness change</th>
            <th>Assessment</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>
    <p class="small muted" style="margin-top:8px">
      Fitness ≈ CTL (long‑term) · Fatigue ≈ ATL (short‑term) · Freshness ≈ TSB (CTL−ATL)
    </p>
  `;
}

async function renderMain(){
  const hist = await fetchJSON(`${API}/api/load?days=90`);
  const series = hist.series || [];

  const xPast = series.map(p => p.date);
  const ctlPast = series.map(p => p.ctl);
  const atlPast = series.map(p => p.atl);
  const tsbPast = series.map(p => p.tsb);

  const lastDate = xPast[xPast.length - 1];
  const lastCtl = ctlPast[ctlPast.length - 1];
  const lastAtl = atlPast[atlPast.length - 1];
  const lastTsb = tsbPast[tsbPast.length - 1];

  // Stable recommendation initialisation (once)
  if(!RECOMMENDED){
    RECOMMENDED = await loadRecommendation();
    setCustomDefaultsAmbitious(RECOMMENDED);
  }

  // Slider (custom only)
  const dur = Number(document.getElementById("dur").value);
  const intensity = Number(document.getElementById("intensity_mode").value);
  const durLbl = document.getElementById("dur_lbl");
  if(durLbl) durLbl.textContent = dur;

  // Rows
  const restRow = computeRestDeltas({ctl:lastCtl, atl:lastAtl, tsb:lastTsb});

  // Recommended deltas: if /api/recommendation provides deltas, use them; else simulate via scenariosDynamic.
  let recRow = RECOMMENDED;
  if(recRow.dur_min and recRow.dur_min > 0 and (recRow.delta_ctl is None or recRow.delta_ctl === 0 and recRow.delta_atl === 0 and recRow.delta_tsb === 0)):
    try:
      const scenRec = await scenariosDynamic(recRow.dur_min, recRow.intensity);
      const sim = (scenRec.scenarios || []).find(s => s.name === "Custom") || scenRec.scenarios[0];
      recRow = { ...recRow, delta_ctl: sim.delta_ctl, delta_atl: sim.delta_atl, delta_tsb: sim.delta_tsb, recommendation: sim.recommendation };
    except:
      pass

  const scenCustom = await scenariosDynamic(dur, intensity);
  const simC = (scenCustom.scenarios || []).find(s => s.name === "Custom") || scenCustom.scenarios[0];
  const customRow = { dur_min: dur, intensity: intensity, delta_ctl: simC.delta_ctl, delta_atl: simC.delta_atl, delta_tsb: simC.delta_tsb, recommendation: simC.recommendation, series: simC.series };

  const recEl = document.getElementById("rec_workout");
  if(recEl){
    recEl.textContent = (RECOMMENDED.dur_min === 0)
      ? "Recommended tomorrow: Rest day."
      : `Recommended tomorrow: ${Math.round(RECOMMENDED.dur_min)} min ${RECOMMENDED.label} (~${Math.round(RECOMMENDED.intensity*100)}% HRmax).`;
  }

  await renderScenarioTable(restRow, recRow, customRow);

  // Explainer panel (uses week zones if available)
  let weekZones = None;
  try:
    const week = await fetchJSON(`${API}/api/zone_effort?weeks=1`);
    weekZones = week.zones;
  except:
    weekZones = None;
  updateRecommendationExplanation(RECOMMENDED, series, weekZones);

  // Main plot: past + custom projection only
  const xFut = nextDatesFrom(lastDate, 7);
  const xProj = [lastDate, ...xFut];
  const withStart = (arr, startVal) => [startVal, ...arr];

  const traces = [
    {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL) past",line:{color:C.ctl,width:3}},
    {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL) past",line:{color:C.atl,width:3}},
    {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB) past",line:{color:C.tsb,width:3}},
    {x:xProj,y:withStart(customRow.series.ctl,lastCtl),type:"scatter",mode:"lines",name:"CTL projection (custom)",line:{color:C.ctl,dash:"dashdot",width:2},opacity:0.9},
    {x:xProj,y:withStart(customRow.series.atl,lastAtl),type:"scatter",mode:"lines",name:"ATL projection (custom)",line:{color:C.atl,dash:"dashdot",width:2},opacity:0.9},
    {x:xProj,y:withStart(customRow.series.tsb,lastTsb),type:"scatter",mode:"lines",name:"TSB projection (custom)",line:{color:C.tsb,dash:"dashdot",width:2},opacity:0.9},
  ];

  Plotly.newPlot("load_plot", traces, {
    ...DARK,
    yaxis:{...DARK.yaxis,title:"load units"},
    xaxis:{...DARK.xaxis,title:"date"},
  }, {responsive:true});

  const meta = document.getElementById("load_meta");
  if(meta) meta.textContent = "Showing last 90 days. Sliders change Custom only; Recommended is stable.";
}

function attachControls(){
  const dur = document.getElementById("dur");
  const mode = document.getElementById("intensity_mode");
  const rerender = () => renderMain().catch(console.error);
  dur.addEventListener("input", rerender);
  mode.addEventListener("change", rerender);
}

document.addEventListener("DOMContentLoaded", () => {
  attachControls();
  renderMain().catch(e => {
    console.error(e);
    alert("Dashboard couldn't load API data. If Render was sleeping, refresh.");
  });
});
