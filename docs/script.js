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
  // lastIsoDate: YYYY-MM-DD
  const base = new Date(lastIsoDate + "T00:00:00Z");
  const out = [];
  for(let i=1;i<=n;i++){
    const d = new Date(base.getTime() + i*24*3600*1000);
    out.push(d.toISOString().slice(0,10));
  }
  return out;
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
  // positive delta ATL = more fatigue; negative = less fatigue
  if(v > 1.0) return "more tired";
  if(v < -1.0) return "less tired";
  return "about the same";
}
function freshnessText(v){
  if(v > 1.0) return "fresher";
  if(v < -1.0) return "more tired";
  return "about the same";
}

async function renderScenarioTable(scen){
  const s = (scen.scenarios || []).slice(0,3);

  const rows = s.map(o => `
    <tr>
      <td><strong>${o.name}</strong></td>
      <td class="num">${arrowFor(o.delta_ctl)} <span class="muted">${fmt(o.delta_ctl,1)}</span></td>
      <td>${fatigueText(o.delta_atl)} <span class="muted">(${fmt(o.delta_atl,1)})</span></td>
      <td>${freshnessText(o.delta_tsb)} <span class="muted">(${fmt(o.delta_tsb,1)})</span></td>
      <td>${recBadge(o.recommendation)}</td>
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
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="small muted" style="margin-top:8px">
      Fitness ≈ CTL (long-term load) · Fatigue ≈ ATL (short-term load) · Freshness ≈ TSB (CTL−ATL)
    </p>
  `;
}

async function renderLoadWithProjections(){
  const dur = Number(document.getElementById("dur").value);
  const intensity = Number(document.getElementById("intensity_mode").value);
  document.getElementById("dur_lbl").textContent = dur;

  // 1) past 90 days only
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

  // 2) scenarios for next 7 days
  const scen = await fetchJSON(`${API}/api/scenarios_dynamic?days=7&dur_min=${dur}&intensity=${intensity}`);
  if(scen.status !== "ok"){
    Plotly.newPlot("load_plot", [
      {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL)",line:{color:C.ctl,width:3}},
      {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL)",line:{color:C.atl,width:3}},
      {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB)",line:{color:C.tsb,width:3,dash:"dot"}},
    ], {...DARK, yaxis:{...DARK.yaxis,title:"load units"}, xaxis:{...DARK.xaxis,title:"date"}}, {responsive:true});
    return;
  }

  await renderScenarioTable(scen);

  const recommended = scen.scenarios[0];
  const rest = (scen.scenarios || []).find(s => s.name === "Rest") || scen.scenarios[1];
  const custom = (scen.scenarios || []).find(s => s.name.startsWith("Custom:")) || scen.scenarios[0];

  // 3) Make projections continuous: start at last past point
  const xFut = nextDatesFrom(lastDate, 7);
  const xProj = [lastDate, ...xFut];

  function withStart(arr, startVal){
    return [startVal, ...arr];
  }

  const styles = [
    { label:"Rest", dash:"dot", width:2, opacity:0.70, scen:rest },
    { label:"Recommended", dash:"dash", width:2.5, opacity:0.85, scen:recommended },
    { label:"Your choice", dash:"dashdot", width:1.5, opacity:0.70, scen:custom },
  ];

  const traces = [
    {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL) past",line:{color:C.ctl,width:3}},
    {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL) past",line:{color:C.atl,width:3}},
    {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB) past",line:{color:C.tsb,width:3}},
  ];

  for(const st of styles){
    const s = st.scen.series;

    traces.push({
      x:xProj, y:withStart(s.ctl, lastCtl),
      type:"scatter", mode:"lines",
      name:`CTL ${st.label}`, line:{color:C.ctl, dash:st.dash, width:st.width}, opacity:st.opacity
    });
    traces.push({
      x:xProj, y:withStart(s.atl, lastAtl),
      type:"scatter", mode:"lines",
      name:`ATL ${st.label}`, line:{color:C.atl, dash:st.dash, width:st.width}, opacity:st.opacity
    });
    traces.push({
      x:xProj, y:withStart(s.tsb, lastTsb),
      type:"scatter", mode:"lines",
      name:`TSB ${st.label}`, line:{color:C.tsb, dash:st.dash, width:st.width}, opacity:st.opacity
    });
  }

  Plotly.newPlot("load_plot", traces, {
    ...DARK,
    yaxis:{...DARK.yaxis,title:"load units"},
    xaxis:{...DARK.xaxis,title:"date"},
  }, {responsive:true});

  document.getElementById("load_meta").textContent =
    `Showing last 90 days. Projections (7d): dotted=rest, dashed=recommended, dash-dot=your choice.`;
}

function attachControls(){
  const dur = document.getElementById("dur");
  const mode = document.getElementById("intensity_mode");
  const rerender = () => renderLoadWithProjections().catch(console.error);
  dur.addEventListener("input", rerender);
  mode.addEventListener("change", rerender);
}

(async function main(){
  try{
    attachControls();
    await renderLoadWithProjections();
  }catch(e){
    console.error(e);
    alert("Dashboard couldn't load API data. If Render was sleeping, refresh.");
  }
})();

/* RUNMETRICS_HR_PANELS_V1 */

async function renderHRPanelsSafely() {
  try {
    const order = ["Z1","Z2","Z3","Z4","Z5"];
    const colors = {
      Z1:"#4da3ff",
      Z2:"#3ddc97",
      Z3:"#ffcc66",
      Z4:"#ff6b6b",
      Z5:"#ff4dff"
    };

    const DARK = {
      paper_bgcolor:"#0f1117",
      plot_bgcolor:"#0f1117",
      font:{color:"#e9eef6"},
      xaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
      yaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
      legend:{orientation:"h", font:{size:10}},
      margin:{t:20,r:10,l:30,b:40},
    };

    const zones = await fetchJSON(`${API}/api/zones`);
    const zonesOld = await fetchJSON(`${API}/api/zones_history?days_ago=90`);
    const week = await fetchJSON(`${API}/api/zone_effort?weeks=1`);

    // ---- Time in zone (stacked bar)
    if (week.status === "ok" && document.getElementById("zones_week_plot")) {
      const mins = order.map(z => week.zones[z]?.minutes || 0);
      const traces = order.map((z,i)=>({
        type:"bar",
        orientation:"h",
        y:["This week"],
        x:[mins[i]],
        name:`${z} (${mins[i]} min)`,
        marker:{color:colors[z]}
      }));

      Plotly.newPlot("zones_week_plot", traces, {
        ...DARK,
        barmode:"stack",
        xaxis:{title:"minutes"},
        yaxis:{visible:false},
      }, {responsive:true});
    }

    // ---- Zones band
    if (zones.status === "ok" && document.getElementById("zones_band_plot")) {
      const shapes = [];

      order.forEach(z=>{
        const [lo,hi] = zones.zones[z];
        shapes.push({
          type:"rect", xref:"x", yref:"paper",
          x0:lo, x1:hi, y0:0, y1:1,
          fillcolor:colors[z]+"55", line:{width:0}
        });
      });

      const addLine = (x, dash, width, opacity) => ({
        type:"line", xref:"x", yref:"paper",
        x0:x, x1:x, y0:0, y1:1,
        line:{color:`rgba(233,238,246,${opacity})`, dash, width}
      });

      shapes.push(addLine(zones.lt1_hr,"solid",2,1));
      shapes.push(addLine(zones.lt2_hr,"solid",2,1));
      shapes.push(addLine(zones.hrmax,"dot",2,0.9));

      if (zonesOld?.status === "ok") {
        shapes.push(addLine(zonesOld.lt1_hr,"dash",1,0.5));
        shapes.push(addLine(zonesOld.lt2_hr,"dash",1,0.5));
      }

      Plotly.newPlot("zones_band_plot", [{
        x:[Math.max(80,0.55*zones.hrmax), zones.hrmax+5],
        y:[0,0],
        mode:"lines",
        line:{color:"rgba(0,0,0,0)"},
        showlegend:false
      }], {
        ...DARK,
        shapes:shapes,
        xaxis:{title:"Heart rate (bpm)"},
        yaxis:{visible:false},
      }, {responsive:true});

      document.getElementById("zones_band_note").textContent =
        `Current: LT1≈${zones.lt1_hr} · LT2≈${zones.lt2_hr} · HRmax≈${zones.hrmax}`;
    }

  } catch (err) {
    console.warn("HR panels skipped:", err);
  }
}

document.addEventListener("DOMContentLoaded", renderHRPanelsSafely);

/* RUNMETRICS_HR_LABELS_AND_SKEW_V1 */
async function renderHRPanelEnhanced() {
  try {
    // Only run if the panels exist
    if (!document.getElementById("zones_week_plot") || !document.getElementById("zones_band_plot")) return;

    const order = ["Z1","Z2","Z3","Z4","Z5"];
    const colors = { Z1:"#4da3ff", Z2:"#3ddc97", Z3:"#ffcc66", Z4:"#ff6b6b", Z5:"#ff4dff" };

    // Use existing fetchJSON/API if present; else fallback
    const API0 = (typeof API !== "undefined") ? API : "https://runmetrics.onrender.com";
    const fetchJSON0 = (typeof fetchJSON !== "undefined") ? fetchJSON : async (url) => {
      const r = await fetch(url); if(!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json();
    };

    const DARK0 = (typeof DARK !== "undefined") ? DARK : {
      paper_bgcolor:"#0f1117",
      plot_bgcolor:"#0f1117",
      font:{color:"#e9eef6"},
      xaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
      yaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
      legend:{orientation:"h", font:{size:10}},
      margin:{t:18,r:10,l:30,b:40},
    };

    const zones = await fetchJSON0(`${API0}/api/zones`);
    const zonesOld = await fetchJSON0(`${API0}/api/zones_history?days_ago=90`);
    const week = await fetchJSON0(`${API0}/api/zone_effort?weeks=1`);

    // ---------- Weekly time-in-zone stacked bar + skew summary ----------
    if (week.status === "ok") {
      const mins = order.map(z => (week.zones[z]?.minutes ?? 0));
      const total = mins.reduce((a,b)=>a+b,0) || 1;
      const frac = mins.map(m => m/total);

      const traces = order.map((z,i)=>({
        type:"bar",
        orientation:"h",
        y:["This week"],
        x:[mins[i]],
        name:`${z} (${mins[i]} min)`,
        marker:{color:colors[z]},
        hovertemplate:`${z}: ${mins[i]} min (${Math.round(100*frac[i])}%)<extra></extra>`
      }));

      Plotly.newPlot("zones_week_plot", traces, {
        ...DARK0,
        barmode:"stack",
        xaxis:{...DARK0.xaxis, title:"minutes"},
        yaxis:{visible:false},
        margin:{t:16,r:10,l:20,b:40},
      }, {responsive:true});

      // Science-based skew summary (cautious language)
      const z1 = frac[0], z2 = frac[1], z3 = frac[2], z4 = frac[3], z5 = frac[4];
      const hard = z4 + z5;

      let summary;
      if (z2 >= 0.55 && z3 < 0.25 && hard < 0.10) {
        summary = "Skew: mostly aerobic (Z2). Likely supports aerobic efficiency / durability (base); may under‑stimulate high‑intensity adaptations (Z4–Z5) if sustained for many weeks.";
      } else if (z3 >= 0.25) {
        summary = "Skew: tempo‑heavy (Z3). Can build muscular endurance and threshold‑adjacent strength, but often carries fatigue—balance with more Z1–Z2 and keep true Z4 sessions deliberate.";
      } else if (hard >= 0.12) {
        summary = "Skew: higher intensity (Z4–Z5). Supports VO₂/speed‑end adaptations, but benefits most when backed by Z2 volume and adequate recovery.";
      } else {
        summary = "Skew: fairly balanced across zones. Good general development; adjust depending on whether you’re building base (more Z2) or sharpening (more Z4).";
      }

      // Put summary just under the weekly plot
      
      let global = document.getElementById("zones_global_skew");
      if (global) {
        global.textContent = summary;
      }
    
    }

    // ---------- HR zone band: label zones + label 90d lines ----------
    if (zones.status !== "ok") return;

    const hrmax = zones.hrmax;
    const lt1 = zones.lt1_hr;
    const lt2 = zones.lt2_hr;

    // Build zone rectangles
    const shapes = [];
    const annotations = [];

    order.forEach(z => {
      const [lo, hi] = zones.zones[z];
      shapes.push({
        type:"rect", xref:"x", yref:"paper",
        x0:lo, x1:hi, y0:0, y1:1,
        fillcolor: colors[z] + "55",
        line:{width:0}
      });

      const mid = (lo + hi) / 2;
      annotations.push({
        x: mid,
        y: 1.08,
        xref: "x",
        yref: "paper",
        text: `${z}  ${Math.round(lo)}–${Math.round(hi)}`,
        showarrow: false,
        font: {color:"#e9eef6", size: 11},
        align: "center"
      });
    });

    // Helper to add labelled vertical lines
    const addVLine = (x, label, dash, opacity) => {
      shapes.push({
        type:"line", xref:"x", yref:"paper",
        x0:x, x1:x, y0:0, y1:1,
        line:{color:`rgba(233,238,246,${opacity})`, width:2, dash:dash}
      });
      annotations.push({
        x: x,
        y: -0.10,
        xref:"x",
        yref:"paper",
        text: label,
        showarrow:false,
        font:{color:`rgba(233,238,246,${opacity})`, size:11},
        align:"center"
      });
    };

    addVLine(lt1, "LT1", "solid", 1.0);
    addVLine(lt2, "LT2", "solid", 1.0);
    addVLine(hrmax, "HRmax", "dot", 0.9);

    if (zonesOld && zonesOld.status === "ok") {
      addVLine(zonesOld.lt1_hr, "LT1 (90d ago)", "dash", 0.55);
      addVLine(zonesOld.lt2_hr, "LT2 (90d ago)", "dash", 0.55);
      addVLine(zonesOld.hrmax, "HRmax (90d ago)", "dot", 0.45);
    }

    Plotly.newPlot("zones_band_plot", [{
      x:[Math.max(80,0.55*hrmax), hrmax+5],
      y:[0,0],
      mode:"lines",
      line:{color:"rgba(0,0,0,0)"},
      showlegend:false
    }], {
      ...DARK0,
      shapes,
      annotations,
      xaxis:{...DARK0.xaxis, title:"Heart rate (bpm)", range:[Math.max(80,0.55*hrmax), hrmax+5]},
      yaxis:{visible:false},
      margin:{t:30,r:10,l:20,b:55},
    }, {responsive:true});

    const note = document.getElementById("zones_band_note");
    if (note) {
      note.textContent = `Current: LT1≈${lt1} bpm · LT2≈${lt2} bpm · HRmax≈${hrmax} bpm (estimates from your data).`;
    }

  } catch (e) {
    console.warn("HR panel enhancement failed (non-fatal):", e);
  }
}

// Run after DOM ready (does not interfere with main panels)
document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("zones_band_plot") && document.getElementById("zones_week_plot")) {
    renderHRPanelEnhanced();
  }
});
