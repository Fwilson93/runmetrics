const API = "https://runmetrics.onrender.com";
document.getElementById("api_url").textContent = API;

function fmt(x, dp=1){
  if(x === null || x === undefined || Number.isNaN(Number(x))) return "";
  return Number(x).toFixed(dp);
}
async function fetchJSON(url){
  // Robust fetch with timeout + one retry. Adds URL/status to errors.
  async function _once(){
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 12000); // 12s
    try{
      const r = await fetch(url, { signal: controller.signal });
      const text = await r.text();
      if(!r.ok){
        throw new Error(`${r.status} ${r.statusText} for ${url} :: ${text.slice(0,200)}`);
      }
      try{
        return JSON.parse(text);
      }catch(e){
        throw new Error(`JSON parse error for ${url} :: ${text.slice(0,200)}`);
      }
    }finally{
      clearTimeout(t);
    }
  }

  try{
    return await _once();
  }catch(e){
    // one retry (helps Render cold start / transient)
    try{
      return await _once();
    }catch(e2){
      throw e2;
    }
  }
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

let RECOMMENDED = null;
let READY = false;

async function loadRecommendation(){
  const rec = await fetchJSON(`${API}/api/recommendation?days=7`);
  if(rec.status === "ok") RECOMMENDED = rec.best;
}

async function renderMain(){
  const dur = Number(document.getElementById("dur").value);
  const intensity = Number(document.getElementById("intensity_mode").value);
  document.getElementById("dur_lbl").textContent = dur;

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

  // Custom depends on sliders
  
  const safeDur = Math.max(dur, 5);
  const safeIntensity = Math.max(intensity, 0.4);
  
  if(!READY) return;
  const scenCustom = await fetchJSON(`${API}/api/scenarios_dynamic?days=7&dur_min=${dur}&intensity=${intensity}`);
  const custom = (scenCustom.scenarios || []).find(s => s.name === "Custom") || scenCustom.scenarios[0];
  
  // Rest computed analytically (no backend call)
  const rest = computeRestDeltas({
    ctl: lastCtl,
    atl: lastAtl,
    tsb: lastTsb
  });
  const xProj = [lastDate, ...xFut];
  const withStart = (arr, startVal) => [startVal, ...arr];

  const traces = [
    {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL) past",line:{color:C.ctl,width:3}},
    {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL) past",line:{color:C.atl,width:3}},
    {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB) past",line:{color:C.tsb,width:3}},
    {x:xProj,y:withStart(custom.series.ctl,lastCtl),type:"scatter",mode:"lines",name:"CTL projection (custom)",line:{color:C.ctl,dash:"dashdot",width:2},opacity:0.9},
    {x:xProj,y:withStart(custom.series.atl,lastAtl),type:"scatter",mode:"lines",name:"ATL projection (custom)",line:{color:C.atl,dash:"dashdot",width:2},opacity:0.9},
    {x:xProj,y:withStart(custom.series.tsb,lastTsb),type:"scatter",mode:"lines",name:"TSB projection (custom)",line:{color:C.tsb,dash:"dashdot",width:2},opacity:0.9},
  ];

  Plotly.newPlot("load_plot", traces, {
    ...DARK,
    yaxis:{...DARK.yaxis,title:"load units"},
    xaxis:{...DARK.xaxis,title:"date"},
  }, {responsive:true});

  document.getElementById("load_meta").textContent =
    `Showing last 90 days. Projection shown for your slider choice only.`;
}

function attachControls(){
  const dur = document.getElementById("dur");
  const mode = document.getElementById("intensity_mode");
  const rerender = () => renderMain().catch(console.error);
  dur.addEventListener("input", rerender);
  mode.addEventListener("change", rerender);
}

document.addEventListener("DOMContentLoaded", async () => {
  try{
    
    
    await loadRecommendation();
    initialiseSlidersSafely();
    
    setCustomDefaultsFromRecommendation(RECOMMENDED);
    READY = true;
    
    attachControls();
    
    await renderMain();

    // Recommendation explanation panel
    try {
      const week = await fetchJSON(`${API}/api/zone_effort?weeks=1`);
      const explain = buildRecommendationExplanation(RECOMMENDED, series, week.zones);
      const el = document.getElementById("recommendation_explain");
      if(el) el.innerHTML = explain;
    } catch(e) {
      const el = document.getElementById("recommendation_explain");
      if(el) el.textContent = "Recommendation details unavailable.";
    }

    // Ensure HR panels render (non-fatal)
    if(typeof renderHRPanels === "function"){
      renderHRPanels().catch(()=>{});
    }
    
  }catch(e){
    
    console.error(e);
    let b = document.getElementById("api_error_banner");
    if(!b){
      b = document.createElement("div");
      b.id = "api_error_banner";
      b.style.margin = "10px 0";
      b.style.padding = "10px 12px";
      b.style.borderRadius = "12px";
      b.style.border = "1px solid rgba(255,204,102,0.35)";
      b.style.background = "rgba(255,204,102,0.10)";
      b.style.color = "#ffcc66";
      b.style.fontSize = "0.95rem";
      document.body.insertBefore(b, document.body.firstChild.nextSibling);
    }
    b.textContent = `API error: ${e.message}. (If Render is waking, retry once.)`;
}
});

/* RECOMMENDATION_EXPLANATION_PANEL_V1 */
function buildRecommendationExplanation(rec, histSeries, weekZones){
  if(!rec || !histSeries.length || !weekZones) return "";

  const last = histSeries[histSeries.length - 1];
  const ctl = last.ctl, atl = last.atl, tsb = last.tsb;

  const order = ["Z1","Z2","Z3","Z4","Z5"];
  const mins = order.map(z => (weekZones[z]?.minutes ?? 0));
  const total = mins.reduce((a,b)=>a+b,0) || 1;
  const frac = mins.map(m => m/total);
  const z2 = frac[1], z3 = frac[2], hard = frac[3] + frac[4];

  let why = [];
  if(tsb < -10){
    why.push("your short‑term fatigue is elevated relative to fitness");
  }
  if(z3 > 0.25){
    why.push("recent training has been weighted toward moderate/tempo intensity");
  }
  if(!why.length){
    why.push("your current fitness–fatigue balance supports steady training");
  }

  let trade = "";
  if(rec.intensity <= 0.68){
    trade = "This prioritises aerobic durability and efficiency, but does not strongly stimulate high‑intensity (Z4–Z5) performance.";
  } else {
    trade = "This targets higher‑intensity adaptations, but increases fatigue and should be balanced with recovery or aerobic work.";
  }

  return `
    <strong>Recommended for tomorrow:</strong>
    ${Math.round(rec.dur_min)} min ${rec.label}.<br>
    ${why.join(", ")}. This makes a controlled session appropriate today.<br>
    <em>Trade‑off:</em> ${trade}
  `;
}

function setCustomDefaultsFromRecommendation(rec){
  if(!rec) return;

  const durEl = document.getElementById("dur");
  const intEl = document.getElementById("intensity_mode");

  // Slightly ambitious but capped
  let newDur = Math.min(rec.dur_min * 1.15, rec.dur_min + 20);
  let newInt = Math.min(rec.intensity + 0.03, 0.80);

  // Prefer duration increase for Z2-type recommendations
  if(rec.intensity <= 0.68){
    durEl.value = Math.round(newDur / 5) * 5;
    intEl.value = rec.intensity;
  } else {
    durEl.value = rec.dur_min;
    intEl.value = newInt.toFixed(2);
  }

  document.getElementById("dur_lbl").textContent = durEl.value;
}

function initialiseSlidersSafely(){
  const durEl = document.getElementById("dur");
  const intEl = document.getElementById("intensity_mode");

  if(Number(durEl.value) < 5){
    durEl.value = 45;
  }
  if(Number(intEl.value) < 0.4){
    intEl.value = 0.65;
  }

  document.getElementById("dur_lbl").textContent = durEl.value;
}

function computeRestDeltas(current){
  // Exponential decay consistent with ATL=7d, CTL=42d
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
