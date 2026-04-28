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


/* RM_LOCK_RECOMMENDED_V1
   Purpose:
   - Keep the Recommended row stable (does not change when sliders move).
   - After the table first renders, set Custom sliders to a slightly more ambitious default.
   - Does not modify your existing rendering logic; it only post-processes the DOM.
*/
(function(){
  let cachedRecommendedHTML = null;
  let ignoreObserver = false;

  function findRecommendedRow(){
    const host = document.getElementById("scenario_table");
    if(!host) return null;
    const rows = host.querySelectorAll("tr");
    let recRow = null;
    rows.forEach(r => {
      const txt = (r.textContent || "").toLowerCase();
      if(txt.includes("recommended")) recRow = r;
    });
    return recRow;
  }

  function cacheOrRestoreRecommended(){
    const recRow = findRecommendedRow();
    if(!recRow) return false;

    // cache first time
    if(cachedRecommendedHTML === null){
      cachedRecommendedHTML = recRow.innerHTML;
      return true;
    }

    // restore if it changed
    if(recRow.innerHTML !== cachedRecommendedHTML){
      ignoreObserver = true;
      recRow.innerHTML = cachedRecommendedHTML;
      ignoreObserver = false;
    }
    return true;
  }

  function setAmbitiousCustomDefaults(){
    const durEl = document.getElementById("dur");
    const intEl = document.getElementById("intensity_mode");
    if(!durEl || !intEl) return;

    // Use current slider values as baseline (these typically match the initial recommended state)
    let dur = parseInt(durEl.value || "45", 10);
    let inten = parseFloat(intEl.value || "0.65");

    // Slightly more ambitious but sensible:
    // - If aerobic-ish, add +15 min duration (cap 90).
    // - Else bump intensity one notch (cap ~0.80), keep duration.
    if(inten <= 0.65){
      dur = Math.min(dur + 15, 90);
    } else {
      const opts = Array.from(intEl.options).map(o => parseFloat(o.value)).sort((a,b)=>a-b);
      const next = opts.find(v => v > inten && v <= 0.80);
      inten = (next !== undefined) ? next : Math.min(inten + 0.03, 0.80);
    }

    // snap duration to 5 min steps
    durEl.value = String(Math.round(dur/5)*5);
    // snap intensity to the select’s value format
    intEl.value = inten.toFixed(2);

    const durLbl = document.getElementById("dur_lbl");
    if(durLbl) durLbl.textContent = durEl.value;

    // Trigger your existing render logic
    durEl.dispatchEvent(new Event("input", { bubbles:true }));
    intEl.dispatchEvent(new Event("change", { bubbles:true }));
  }

  function boot(){
    const host = document.getElementById("scenario_table");
    if(!host) return;

    // Wait until table is rendered once, then cache recommended and set defaults.
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      const ok = cacheOrRestoreRecommended();
      if(ok){
        clearInterval(timer);

        // Observe future changes and keep recommended stable
        const obs = new MutationObserver(() => {
          if(ignoreObserver) return;
          cacheOrRestoreRecommended();
        });
        obs.observe(host, { childList:true, subtree:true, characterData:true });

        // After caching recommended, make custom a bit more ambitious
        setTimeout(setAmbitiousCustomDefaults, 80);
      }
      if(tries > 60) clearInterval(timer); // give up after ~12s
    }, 200);
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();


/* RM_RECOMMENDATION_EXPLAIN_PANEL_V1
   Reads the rendered "Recommended" table row and explains it.
   No API calls, no dependency on sliders.
*/
(function(){
  function inferExplanation(text){
    const t = text.toLowerCase();

    if(t.includes("rest")){
      return {
        why: "Fatigue is high relative to fitness, so recovery is prioritised.",
        trade: "Fitness progression pauses temporarily to restore freshness."
      };
    }

    if(t.includes("z2") || t.includes("aerobic")){
      return {
        why: "Aerobic work supports cardiovascular efficiency and durability with low fatigue cost.",
        trade: "Minimal high-intensity (Z4–Z5) stimulus today."
      };
    }

    if(t.includes("steady")){
      return {
        why: "Steady intensity builds aerobic strength while keeping fatigue manageable.",
        trade: "Less top-end speed or VO₂ stimulus compared to harder sessions."
      };
    }

    if(t.includes("tempo") || t.includes("hard")){
      return {
        why: "Moderate–high intensity supports threshold and race-relevant fitness.",
        trade: "Higher fatigue load — balance with easier days."
      };
    }

    return {
      why: "This option balances fitness progression and fatigue given your recent training.",
      trade: "Some adaptations are deprioritised today."
    };
  }

  function updatePanel(){
    const host = document.getElementById("scenario_table");
    const panel = document.getElementById("recommendation_explain");
    if(!host || !panel) return;

    const rows = host.querySelectorAll("tr");
    let recRow = null;

    rows.forEach(r => {
      if((r.textContent || "").toLowerCase().includes("recommended")){
        recRow = r;
      }
    });

    if(!recRow) return;

    const text = recRow.textContent || "";
    const info = inferExplanation(text);

    panel.innerHTML = `
      <strong>Why this is recommended</strong><br>
      ${info.why}<br>
      <em>Trade-off:</em> ${info.trade}
    `;
  }

  function boot(){
    // Table renders asynchronously; poll briefly then observe
    let tries = 0;
    const timer = setInterval(() => {
      updatePanel();
      tries += 1;
      if(tries > 25){
        clearInterval(timer);
        const host = document.getElementById("scenario_table");
        if(host){
          const obs = new MutationObserver(updatePanel);
          obs.observe(host, { childList:true, subtree:true, characterData:true });
        }
      }
    }, 200);
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();


/* RM_RUNNING_LOAD_CALIBRATION_V1
   Calibrate a running-specific load scale from recent history.
   Applied ONLY to projections (not past CTL).
*/
async function computeRunScale(){
  try{
    const hist = await fetchJSON(`${API}/api/load?days=56`);
    const s = hist.series || [];
    if(s.length < 14) return 0.5; // fallback

    // realised CTL ramp
    const ctl_start = s[0].ctl;
    const ctl_end = s[s.length-1].ctl;
    const weeks = s.length / 7.0;
    const realised_per_week = (ctl_end - ctl_start) / weeks;

    // plausible running ramp (centre of typical sustainable range)
    const target_per_week = Math.max(2.5, Math.min(7.0, realised_per_week));

    // model ramp implied by raw load (protect against divide-by-zero)
    const model_per_week = realised_per_week !== 0 ? realised_per_week : 5.0;

    const k = target_per_week / model_per_week;
    return Math.max(0.25, Math.min(1.0, k));
  }catch(e){
    console.warn("Run scale calibration failed; using fallback", e);
    return 0.5;
  }
}


/* RM_RECOMMENDATION_EXPLAIN_V4_SAFE
   - Does NOT move panels
   - Reads the 'Recommended' row from #scenario_table
   - Adds context from /api/load (42d) and optionally /api/zone_effort (weeks=1)
   - Never throws; fails quietly and leaves existing text in place
*/
(function(){
  function el(id){ return document.getElementById(id); }

  async function fetchJSONSafe(url, timeoutMs){
    const tMs = timeoutMs || 12000;
    try{
      const controller = new AbortController();
      const t = setTimeout(()=>controller.abort(), tMs);
      const r = await fetch(url, {signal: controller.signal});
      clearTimeout(t);
      if(!r.ok) return null;
      return await r.json();
    }catch(_e){
      return null;
    }
  }

  function findRecommendedText(){
    const host = el("scenario_table");
    if(!host) return null;
    const rows = host.querySelectorAll("tr");
    for(const r of rows){
      const txt = (r.textContent || "").trim();
      if(txt.toLowerCase().includes("recommended")) return txt;
    }
    return null;
  }

  function parseRec(recText){
    const t = recText.toLowerCase();
    const m = t.match(/(\d+)\s*min/);
    const minutes = m ? parseInt(m[1], 10) : null;

    let kind = "aerobic";
    if(t.includes("rest")) kind = "rest";
    else if(t.includes("tempo")) kind = "tempo";
    else if(t.includes("steady")) kind = "steady";
    else if(t.includes("z2") || t.includes("aerobic")) kind = "aerobic";

    return {minutes, kind, raw: recText};
  }

  function computeContext(load42){
    if(!load42 || !Array.isArray(load42.series) || load42.series.length < 14) return null;
    const s = load42.series;
    const last = s[s.length-1];

    const sum = arr => arr.reduce((a,b)=>a+(b.daily_load||0),0);
    const last7 = s.slice(-7);
    const prev28 = s.length >= 35 ? s.slice(-35, -7) : [];

    const last7Load = sum(last7);
    const prev28Load = prev28.length ? sum(prev28) : null;
    const prev28Weekly = (prev28Load !== null) ? (prev28Load/4.0) : null;

    // days since last non-zero daily_load
    let daysSince = null;
    for(let i=s.length-1;i>=0;i--){
      if((s[i].daily_load||0) > 0){
        const d = new Date(s[i].date + "T00:00:00Z");
        const now = new Date();
        daysSince = Math.floor((now-d)/(24*3600*1000));
        break;
      }
    }

    return {
      ctl: last.ctl, atl: last.atl, tsb: last.tsb,
      last7Load: last7Load,
      prev28Weekly: prev28Weekly,
      daysSince: daysSince
    };
  }

  function computeSkew(zoneEffort){
    try{
      if(!zoneEffort || zoneEffort.status !== "ok") return null;
      const z = zoneEffort.zones;
      const order = ["Z1","Z2","Z3","Z4","Z5"];
      const mins = order.map(k => (z[k] && z[k].minutes) ? z[k].minutes : 0);
      const tot = mins.reduce((a,b)=>a+b,0) || 1;
      const frac = mins.map(m=>m/tot);
      return {z2: frac[1], z3: frac[2], hard: frac[3]+frac[4]};
    }catch(_e){
      return null;
    }
  }

  function buildWhy(rec, ctx, skew){
    const linesIntensity = [];
    const linesDuration = [];
    const linesTrade = [];

    if(ctx){
      if(ctx.tsb < -15) linesIntensity.push("Freshness is low (you’re carrying fatigue), so the recommendation biases toward recoverable stimulus.");
      else if(ctx.tsb < -5) linesIntensity.push("Freshness is slightly suppressed (mild fatigue), so intensity is chosen to stay productive without overreaching.");
      else linesIntensity.push("Freshness is reasonable, so a normal training stimulus is appropriate.");
    }

    if(ctx && ctx.prev28Weekly !== null){
      if(ctx.last7Load < 0.75*ctx.prev28Weekly){
        linesDuration.push("Your last 7 days’ training load is below your recent baseline; the duration aims to rebuild consistency safely.");
      } else if(ctx.last7Load > 1.15*ctx.prev28Weekly){
        linesDuration.push("Your last 7 days’ load is high relative to baseline; the duration aims to avoid piling fatigue on top.");
      } else {
        linesDuration.push("Your recent weekly load is close to baseline; this duration provides a useful stimulus without unnecessary risk.");
      }
    } else {
      linesDuration.push("The duration is selected to provide meaningful stimulus while remaining recoverable given your recent pattern.");
    }

    if(skew){
      if(skew.z3 > 0.25) linesIntensity.push("This week has been more tempo‑weighted (Z3), so today’s choice leans toward controllable work.");
      if(skew.hard > 0.12) linesIntensity.push("There’s been a fair share of higher intensity (Z4–Z5), so the recommendation consolidates rather than adds more stress.");
      if(skew.z2 > 0.55) linesIntensity.push("You’re already skewed toward aerobic work (Z2), which supports base-building; this continues that safely.");
    }

    if(rec.kind === "rest"){
      linesIntensity.push("Rest is recommended when additional training stress is unlikely to pay back today.");
      linesTrade.push("Trade‑off: fitness does not increase today, but freshness improves faster, setting up higher‑quality sessions next.");
    } else if(rec.kind === "aerobic"){
      linesIntensity.push("Aerobic intensity builds cardiovascular/mitochondrial efficiency and durability at a relatively low fatigue cost.");
      linesTrade.push("Trade‑off: minimal high‑intensity (Z4–Z5) stimulus today (more ‘base’ than ‘sharpening’).");
    } else if(rec.kind === "steady"){
      linesIntensity.push("Steady intensity develops aerobic strength while remaining sub‑threshold, balancing stimulus and fatigue.");
      linesTrade.push("Trade‑off: more fatigue than easy aerobic, less top‑end stimulus than tempo/intervals.");
    } else if(rec.kind === "tempo"){
      linesIntensity.push("Tempo targets threshold‑adjacent adaptations and sustained strength when freshness allows.");
      linesTrade.push("Trade‑off: higher fatigue cost — usually benefits from easier surrounding days.");
    }

    if(rec.minutes){
      if(rec.minutes <= 35) linesDuration.push("A shorter duration reduces fatigue while maintaining the habit of training.");
      else if(rec.minutes <= 70) linesDuration.push("This is long enough to generate aerobic stimulus without being a ‘big day’.");
      else linesDuration.push("Longer duration emphasises durability; recover well after.");
    }

    return {
      intensity: linesIntensity.join(" "),
      duration: linesDuration.join(" "),
      trade: linesTrade.join(" ")
    };
  }

  async function updateExplain(){
    const panel = el("recommendation_explain");
    if(!panel) return;

    const recText = findRecommendedText();
    if(!recText) return;

    const rec = parseRec(recText);

    const load42 = await fetchJSONSafe(`${API}/api/load?days=42`, 12000);
    const ctx = computeContext(load42);

    const ze = await fetchJSONSafe(`${API}/api/zone_effort?weeks=1`, 12000);
    const skew = computeSkew(ze);

    const why = buildWhy(rec, ctx, skew);

    panel.innerHTML = `
      <h3>Why this is recommended</h3>
      <p class="explain"><strong>Recommendation:</strong> ${rec.raw}</p>
      <p class="explain"><strong>Why this intensity:</strong> ${why.intensity}</p>
      <p class="explain"><strong>Why this duration:</strong> ${why.duration}</p>
      <p class="explain"><strong>Trade‑off:</strong> ${why.trade}</p>
      <p class="explain muted">Note: This is decision support based on recent load trends. Interpret directionally rather than as a precise physiological forecast.</p>
    `;
  }

  function boot(){
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      updateExplain();
      if(tries >= 15){
        clearInterval(timer);
        const host = el("scenario_table");
        if(host){
          const obs = new MutationObserver(() => { updateExplain(); });
          obs.observe(host, {childList:true, subtree:true, characterData:true});
        }
      }
    }, 250);
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
