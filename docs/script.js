const API = "https://runmetrics.onrender.com";
document.getElementById("api_url").textContent = API;

function fmt(x, dp=1){
  if(x === null || x === undefined || Number.isNaN(Number(x))) return "";
  return Number(x).toFixed(dp);
}
async function fetchJSON(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
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
  const scenCustom = await fetchJSON(`${API}/api/scenarios_dynamic?days=7&dur_min=${dur}&intensity=${intensity}`);
  const custom = (scenCustom.scenarios || []).find(s => s.name === "Custom") || scenCustom.scenarios[0];
  const rest = (scenCustom.scenarios || []).find(s => s.name === "Rest") || scenCustom.scenarios[0];

  // Recommended is stable
  const rec = RECOMMENDED || (await fetchJSON(`${API}/api/recommendation?days=7`)).best;

  document.getElementById("rec_workout").textContent =
    rec.dur_min === 0 ? "Recommended tomorrow: Rest day." :
    `Recommended tomorrow: ${Math.round(rec.dur_min)} min ${rec.label}.`;

  const rows = [
    {label:"Rest", dctl:rest.delta_ctl, datl:rest.delta_atl, dtsb:rest.delta_tsb, rec:rest.recommendation},
    {label:`Recommended (${Math.round(rec.dur_min)} min ${intensityLabel(rec.intensity)})`, dctl:rec.delta_ctl, datl:rec.delta_atl, dtsb:rec.delta_tsb, rec:rec.recommendation},
    {label:"Custom", dctl:custom.delta_ctl, datl:custom.delta_atl, dtsb:custom.delta_tsb, rec:custom.recommendation},
  ];

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
        <tbody>
          ${rows.map(r=>`
            <tr>
              <td><strong>${r.label}</strong></td>
              <td class="num">${arrowFor(r.dctl)} <span class="muted">${fmt(r.dctl,1)}</span></td>
              <td>${fatigueText(r.datl)} <span class="muted">(${fmt(r.datl,1)})</span></td>
              <td>${freshnessText(r.dtsb)} <span class="muted">(${fmt(r.dtsb,1)})</span></td>
              <td>${recBadge(r.rec)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  // Past solid + custom-only projection
  const xFut = nextDatesFrom(lastDate, 7);
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
    attachControls();
    await renderMain();
  }catch(e){
    console.error(e);
    alert("Dashboard couldn't load API data. If Render was sleeping, refresh.");
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
