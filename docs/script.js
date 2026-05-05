/* RunMetrics static dashboard (GitHub Pages)
   - Reads precomputed JSON from docs/data/*
   - Performs scenario projections client-side
*/
const DATA = "./data";

function fmt(x, dp=1){
  if(x === null || x === undefined || Number.isNaN(Number(x))) return "";
  return Number(x).toFixed(dp);
}
async function fetchJSON(url){
  const r = await fetch(url, { cache: "no-cache" });
  if(!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`);
  return r.json();
}

const DARK = {
  paper_bgcolor:"#0f1117",
  plot_bgcolor:"#0f1117",
  font:{color:"#e9eef6"},
  xaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
  yaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
  legend:{orientation:"h"},
  margin:{t:20,r:10,l:60,b:45},
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
function arrowFor(v){
  if(v > 1.0) return "↑";
  if(v < -1.0) return "↓";
  return "↔";
}
function fatigueText(v){
  if(v > 1.0) return "more tired";
  if(v < -1.0) return "less tired";
  return "about the same";
}
function freshnessText(v){
  if(v > 1.0) return "fresher";
  if(v < -1.0) return "more tired";
  return "about the same";
}

// CTL/ATL update form: prev + (x - prev)/tau
function ewmaUpdate(prev, x, tau){
  return prev + (x - prev) / tau;
}

function simulateProjection(lastCtl, lastAtl, addLoadTomorrow, horizonDays, tauCtl=42, tauAtl=7){
  let ctl = lastCtl;
  let atl = lastAtl;
  const outCtl = [];
  const outAtl = [];
  const outTsb = [];
  for(let i=0;i<horizonDays;i++){
    const x = (i===0) ? addLoadTomorrow : 0.0;
    ctl = ewmaUpdate(ctl, x, tauCtl);
    atl = ewmaUpdate(atl, x, tauAtl);
    outCtl.push(ctl);
    outAtl.push(atl);
    outTsb.push(ctl - atl);
  }
  return { ctl: outCtl, atl: outAtl, tsb: outTsb };
}

function estimateWorkoutLoad(durMin, intensity, hrmax){
  // Mirror the same load scale as the Python proxy:
  // duration_min * intensity^2 * 100
  // intensity is treated as fraction of HRmax
  return durMin * (intensity*intensity) * 100.0;
}

async function renderHRPanels(){
  const order = ["Z1","Z2","Z3","Z4","Z5"];
  const colors = { Z1:"#4da3ff", Z2:"#3ddc97", Z3:"#ffcc66", Z4:"#ff6b6b", Z5:"#ff4dff" };

  let zones, week;
  try{
    zones = await fetchJSON(`${DATA}/zones.json`);
    week = await fetchJSON(`${DATA}/zone_effort_1w.json`);
  }catch(e){
    console.warn("Zones unavailable:", e);
    return;
  }

  if (week && week.status === "ok") {
    const mins = order.map(z => (week.zones?.[z]?.minutes ?? 0));
    const traces = order.map((z,i)=>({
      type:"bar", orientation:"h",
      y:["This week"], x:[mins[i]],
      name:`${z} (${mins[i]} min)`,
      marker:{color:colors[z]},
    }));
    Plotly.newPlot("zones_week_plot", traces, {
      ...DARK,
      barmode:"stack",
      xaxis:{...DARK.xaxis, title:"minutes"},
      margin:{t:16,r:10,l:20,b:40}
    }, {displayModeBar:false});
  }

  if (zones && zones.status === "ok") {
    const hrmax = zones.hrmax;
    const lt1 = zones.lt1_hr;
    const lt2 = zones.lt2_hr;
    const el = document.getElementById("hr_meta");
    if(el){
      el.innerHTML = `HRmax (observed/assumed): <strong>${Math.round(hrmax)}</strong> bpm · LT1≈ <strong>${Math.round(lt1)}</strong> · LT2≈ <strong>${Math.round(lt2)}</strong><br><span class="muted small">${zones.note ?? ""}</span>`;
    }
  }
}

async function renderMain(){
  // Controls
  const dur = Number(document.getElementById("dur").value);
  const intensity = Number(document.getElementById("intensity_mode").value);
  document.getElementById("dur_lbl").textContent = dur;

  // Load series (365 days) and slice last 90 for plot
  const hist = await fetchJSON(`${DATA}/load_365.json`);
  const series = hist.series ?? [];

  const last90 = series.slice(Math.max(0, series.length - 90));
  const xPast = last90.map(p => p.date);
  const ctlPast = last90.map(p => p.ctl);
  const atlPast = last90.map(p => p.atl);
  const tsbPast = last90.map(p => p.tsb);

  const last = series[series.length - 1];
  const lastDate = last.date;
  const lastCtl = last.ctl;
  const lastAtl = last.atl;
  const lastTsb = last.tsb;

  const xFut = nextDatesFrom(lastDate, 7);
  const xProj = [lastDate, ...xFut];

  // Scenario options
  const hrmax = hist.hrmax ?? 190;
  const restLoad = 0.0;
  const customLoad = estimateWorkoutLoad(dur, intensity, hrmax);

  const rest = simulateProjection(lastCtl, lastAtl, restLoad, 7);
  const custom = simulateProjection(lastCtl, lastAtl, customLoad, 7);

  function deltas(proj){
    const ctlF = proj.ctl[proj.ctl.length - 1];
    const atlF = proj.atl[proj.atl.length - 1];
    const tsbF = proj.tsb[proj.tsb.length - 1];
    return { delta_ctl: ctlF - lastCtl, delta_atl: atlF - lastAtl, delta_tsb: tsbF - lastTsb, tsb_final: tsbF };
  }

  const dRest = deltas(rest);
  const dCustom = deltas(custom);

  // Recommended: choose between Rest and Custom by best final TSB, but avoid very negative TSB
  const recommended = (dCustom.tsb_final >= dRest.tsb_final) ? "Custom" : "Rest";
  const recObj = (recommended === "Custom") ? dCustom : dRest;

  function assessment(tsbFinal){
    if (tsbFinal > -5) return "good";
    if (tsbFinal > -15) return "caution";
    return "risky";
  }

  // Table
  const rows = [
    { label:"Rest", d:dRest, rec:assessment(dRest.tsb_final) },
    { label:(recommended==="Custom" ? `Recommended (${Math.round(dur)} min ${intensityLabel(intensity)})` : "Recommended (Rest)"), d:recObj, rec:assessment(recObj.tsb_final) },
    { label:"Custom", d:dCustom, rec:assessment(dCustom.tsb_final) },
  ];

  const tableRows = rows.map(r => `
    <tr>
      <td><strong>${r.label}</strong></td>
      <td class="num">${arrowFor(r.d.delta_ctl)} <span class="muted">${fmt(r.d.delta_ctl,1)}</span></td>
      <td>${fatigueText(r.d.delta_atl)} <span class="muted">(${fmt(r.d.delta_atl,1)})</span></td>
      <td>${freshnessText(r.d.delta_tsb)} <span class="muted">(${fmt(r.d.delta_tsb,1)})</span></td>
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

  // Plot: past + custom projection
  const withStart = (arr, startVal) => [startVal, ...arr];

  const traces = [
    {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL) past",line:{color:C.ctl,width:3}},
    {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL) past",line:{color:C.atl,width:3}},
    {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB) past",line:{color:C.tsb,width:3}},
    {x:xProj,y:withStart(custom.ctl, lastCtl),type:"scatter",mode:"lines",name:"CTL projection (your choice)",line:{color:C.ctl, dash:"dashdot", width:2},opacity:0.85},
    {x:xProj,y:withStart(custom.atl, lastAtl),type:"scatter",mode:"lines",name:"ATL projection (your choice)",line:{color:C.at
