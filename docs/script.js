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
  legend:{orientation:"h", font:{size:10}},
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

function daysSinceLastTraining(loadSeries){
  // loadSeries items have {date, daily_load, ctl, atl, tsb}
  // Find last day with daily_load > 0
  for (let i = loadSeries.length - 1; i >= 0; i--) {
    if ((loadSeries[i].daily_load || 0) > 0) {
      const d = new Date(loadSeries[i].date + "T00:00:00Z");
      const now = new Date();
      const diff = Math.floor((now - d) / (24*3600*1000));
      return diff;
    }
  }
  return 999;
}

function summariseSkew(weekZones){
  const order = ["Z1","Z2","Z3","Z4","Z5"];
  const mins = order.map(z => (weekZones[z]?.minutes ?? 0));
  const total = mins.reduce((a,b)=>a+b,0) || 1;
  const frac = mins.map(m => m/total);
  const [z1,z2,z3,z4,z5] = frac;
  const hard = z4 + z5;

  if (z2 >= 0.55 && z3 < 0.25 && hard < 0.10) {
    return "Skew: mostly aerobic (Z2). Likely supports aerobic durability/efficiency; may under‑stimulate high‑intensity (Z4–Z5) adaptations if sustained for many weeks.";
  } else if (z3 >= 0.25) {
    return "Skew: tempo‑heavy (Z3). Can build muscular endurance and threshold‑adjacent strength, but often carries fatigue—balance with more Z1–Z2 and keep Z4 sessions deliberate.";
  } else if (hard >= 0.12) {
    return "Skew: higher intensity (Z4–Z5). Supports VO₂/speed adaptations, but benefits most when backed by Z2 volume and adequate recovery.";
  } else {
    return "Skew: fairly balanced. Good general development; shift towards more Z2 for base phases or more Z4 for sharpening phases.";
  }
}

async function renderHRPanels(){
  const order = ["Z1","Z2","Z3","Z4","Z5"];
  const colors = { Z1:"#4da3ff", Z2:"#3ddc97", Z3:"#ffcc66", Z4:"#ff6b6b", Z5:"#ff4dff" };

  const zones = await fetchJSON(`${API}/api/zones`);
  const zonesOld = await fetchJSON(`${API}/api/zones_history?days_ago=90`);
  const week = await fetchJSON(`${API}/api/zone_effort?weeks=1`);

  // Weekly stacked bar
  if (week.status === "ok") {
    const mins = order.map(z => week.zones[z]?.minutes || 0);
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
      yaxis:{visible:false},
      margin:{t:16,r:10,l:20,b:40}
    }, {responsive:true});

    document.getElementById("zones_global_skew").textContent = summariseSkew(week.zones);
  }

  // Zone band
  if (zones.status === "ok") {
    const hrmax = zones.hrmax;
    const lt1 = zones.lt1_hr;
    const lt2 = zones.lt2_hr;

    const shapes = [];
    const annotations = [];

    order.forEach(z => {
      const [lo,hi] = zones.zones[z];
      shapes.push({
        type:"rect", xref:"x", yref:"paper",
        x0:lo, x1:hi, y0:0, y1:1,
        fillcolor: colors[z] + "55",
        line:{width:0}
      });

      // Put zone label above, small font to avoid overlap
      annotations.push({
        x:(lo+hi)/2, y:1.08, xref:"x", yref:"paper",
        text:`${z} ${Math.round(lo)}–${Math.round(hi)}`,
        showarrow:false,
        font:{color:"rgba(233,238,246,0.85)", size:10},
        align:"center"
      });
    });

    const addVLine = (x, label, dash, opacity, width=2) => {
      shapes.push({
        type:"line", xref:"x", yref:"paper",
        x0:x, x1:x, y0:0, y1:1,
        line:{color:`rgba(233,238,246,${opacity})`, dash, width}
      });
      annotations.push({
        x:x, y:-0.12, xref:"x", yref:"paper",
        text:label, showarrow:false,
        font:{color:`rgba(233,238,246,${opacity})`, size:10},
        align:"center"
      });
    };

    addVLine(lt1, "LT1", "solid", 1.0, 2);
    addVLine(lt2, "LT2", "solid", 1.0, 2);
    addVLine(hrmax, "HRmax", "dot", 0.9, 2);

    if (zonesOld && zonesOld.status === "ok") {
      addVLine(zonesOld.lt1_hr, "LT1 (90d ago)", "dash", 0.55, 1);
      addVLine(zonesOld.lt2_hr, "LT2 (90d ago)", "dash", 0.55, 1);
      addVLine(zonesOld.hrmax, "HRmax (90d ago)", "dot", 0.40, 1);
    }

    Plotly.newPlot("zones_band_plot", [{
      x:[Math.max(80,0.55*hrmax), hrmax+5],
      y:[0,0],
      mode:"lines",
      line:{color:"rgba(0,0,0,0)"},
      showlegend:false
    }], {
      ...DARK,
      shapes,
      annotations,
      xaxis:{...DARK.xaxis, title:"Heart rate (bpm)", range:[Math.max(80,0.55*hrmax), hrmax+5]},
      yaxis:{visible:false},
      margin:{t:32,r:10,l:20,b:58},
      showlegend:false
    }, {responsive:true});

    document.getElementById("zones_band_note").textContent =
      `Current: LT1≈${lt1} bpm · LT2≈${lt2} bpm · HRmax≈${hrmax} bpm (estimated from your data).`;
  }
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

  const scen = await fetchJSON(`${API}/api/scenarios_dynamic?days=7&dur_min=${dur}&intensity=${intensity}`);
  if (scen.status !== "ok") throw new Error("scenarios_dynamic failed");

  // Identify scenarios
  const rest = (scen.scenarios || []).find(s => s.name === "Rest");
  const custom = (scen.scenarios || []).find(s => s.name === "Custom") || scen.scenarios[0];

  // Recommended = best non-rest if available, else best overall
  let recommended = scen.scenarios[0];
  const bestNonRest = (scen.scenarios || []).find(s => s.name !== "Rest");
  if (bestNonRest) recommended = bestNonRest;

  // Recommended workout text
  if (recommended.name === "Rest" || recommended.dur_min === 0) {
    document.getElementById("rec_workout").textContent =
      "Recommended tomorrow: Rest day (based on freshness projection).";
  } else {
    document.getElementById("rec_workout").textContent =
      `Recommended tomorrow: ${Math.round(recommended.dur_min)} min at ${intensityLabel(recommended.intensity)} (~${Math.round(recommended.intensity*100)}% HRmax).`;
  }

  // Table rows: Rest, Recommended(desc), Custom
  const daysOff = daysSinceLastTraining(series);
  const fatigueHigh = (scen.baseline && scen.baseline.tsb < -15) || (scen.baseline && scen.baseline.atl > 1.05*scen.baseline.ctl);

  function assessmentFor(option){
    let rec = option.recommendation || "good";
    if (option.name === "Rest" && daysOff > 2 && !fatigueHigh) {
      rec = "caution";
    }
    return rec;
  }

  const rows = [];

  if (rest) {
    rows.push({
      label:"Rest",
      delta_ctl:rest.delta_ctl, delta_atl:rest.delta_atl, delta_tsb:rest.delta_tsb,
      rec:assessmentFor(rest)
    });
  }

  const recDesc = (recommended.name === "Rest" || recommended.dur_min === 0)
    ? "Recommended (Rest)"
    : `Recommended (${Math.round(recommended.dur_min)} min ${intensityLabel(recommended.intensity)})`;

  rows.push({
    label:recDesc,
    delta_ctl:recommended.delta_ctl, delta_atl:recommended.delta_atl, delta_tsb:recommended.delta_tsb,
    rec:assessmentFor(recommended)
  });

  rows.push({
    label:"Custom",
    delta_ctl:custom.delta_ctl, delta_atl:custom.delta_atl, delta_tsb:custom.delta_tsb,
    rec:assessmentFor(custom)
  });

  const tableRows = rows.map(r => `
    <tr>
      <td><strong>${r.label}</strong></td>
      <td class="num">${arrowFor(r.delta_ctl)} <span class="muted">${fmt(r.delta_ctl,1)}</span></td>
      <td>${fatigueText(r.delta_atl)} <span class="muted">(${fmt(r.delta_atl,1)})</span></td>
      <td>${freshnessText(r.delta_tsb)} <span class="muted">(${fmt(r.delta_tsb,1)})</span></td>
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

  try {
    const recRow = rows.find(r => r.label.startsWith("Recommended"));
    updateRecommendationExplanation(recRow);
  } catch(e){}

  // MAIN PLOT: past solid; ONLY custom projection
  const xFut = nextDatesFrom(lastDate, 7);
  const xProj = [lastDate, ...xFut];
  const withStart = (arr, startVal) => [startVal, ...arr];

  const traces = [
    {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL) past",line:{color:C.ctl,width:3}},
    {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL) past",line:{color:C.atl,width:3}},
    {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB) past",line:{color:C.tsb,width:3}},
  ];

  traces.push({
    x:xProj, y:withStart(custom.series.ctl, lastCtl),
    type:"scatter", mode:"lines",
    name:"CTL projection (your choice)",
    line:{color:C.ctl, dash:"dashdot", width:2}, opacity:0.85
  });
  traces.push({
    x:xProj, y:withStart(custom.series.atl, lastAtl),
    type:"scatter", mode:"lines",
    name:"ATL projection (your choice)",
    line:{color:C.atl, dash:"dashdot", width:2}, opacity:0.85
  });
  traces.push({
    x:xProj, y:withStart(custom.series.tsb, lastTsb),
    type:"scatter", mode:"lines",
    name:"TSB projection (your choice)",
    line:{color:C.tsb, dash:"dashdot", width:2}, opacity:0.85
  });

  Plotly.newPlot("load_plot", traces, {
    ...DARK,
    yaxis:{...DARK.yaxis,title:"load units"},
    xaxis:{...DARK.xaxis,title:"date"},
  }, {responsive:true});

  document.getElementById("load_meta").textContent =
    `Showing last 90 days. Projection shown for your slider choice only.`;

  // HR panels (non-blocking)
  renderHRPanels().catch(err => console.warn("HR panels skipped:", err));
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

/* RECOMMENDATION_EXPLAIN_V1 */
function updateRecommendationExplanation(recRow){
  const el = document.getElementById("recommendation_explain");
  if(!el || !recRow) return;

  let intensityText = "aerobic (Z2)";
  if(recRow.label.toLowerCase().includes("tempo")) intensityText = "tempo";
  if(recRow.label.toLowerCase().includes("steady")) intensityText = "steady aerobic";

  let tradeoff =
    intensityText === "aerobic (Z2)"
    ? "This prioritises aerobic efficiency and durability, but does not strongly stimulate high-intensity (Z4–Z5) performance."
    : "This stresses higher-intensity systems, but adds fatigue and should be balanced with easier aerobic work.";

  el.innerHTML = `
    <strong>Recommended for tomorrow:</strong>
    ${recRow.label}.<br>
    This is suggested to support fitness progression while keeping fatigue under control based on your recent load and projected freshness.<br>
    <em>Trade-off:</em> ${tradeoff}
  `;
}
