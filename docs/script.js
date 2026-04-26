const API = "https://runmetrics.onrender.com";

const statusEl = document.getElementById("status");
const btnMetrics = document.getElementById("recompute");
const btnPMC = document.getElementById("recompute_pmc");
const tbody = document.querySelector("#activities tbody");

const ctlVal = document.getElementById("ctl_val");
const atlVal = document.getElementById("atl_val");
const tsbVal = document.getElementById("tsb_val");
const ctlDelta = document.getElementById("ctl_delta");
const atlDelta = document.getElementById("atl_delta");
const tsbDelta = document.getElementById("tsb_delta");

function setStatus(msg){ statusEl.textContent = msg; }
function fmt(x, d=1){ if (x===null||x===undefined) return "–"; return Number(x).toFixed(d); }
function fmtDate(iso){ if (!iso) return ""; return iso.slice(0,10); }

async function recomputeMetrics(){
  setStatus("Recomputing metrics…");
  const r = await fetch(`${API}/metrics/derive`);
  const j = await r.json();
  setStatus(`Metrics ok (${j.activities} activities)`);
}

async function recomputePMC(){
  setStatus("Recomputing PMC…");
  // Defaults: HRrest=50, HRmax=190, male, CTL=42, ATL=7
  const r = await fetch(`${API}/pmc/recompute`);
  const j = await r.json();
  if (j.status === "ok") setStatus(`PMC ok (${j.days} days)`);
  else setStatus("PMC recompute failed");
}

async function getActivities(){
  const r = await fetch(`${API}/api/activities?limit=60`);
  const j = await r.json();
  return j.activities || [];
}

async function getMetricsSeries(){
  const r = await fetch(`${API}/api/metrics?limit=300`);
  const j = await r.json();
  return j.metrics || [];
}

async function getPMC(days=120){
  const r = await fetch(`${API}/api/pmc?days=${days}`);
  const j = await r.json();
  return j.pmc || [];
}

async function getStatus(){
  const r = await fetch(`${API}/api/status`);
  return await r.json();
}

function renderTable(acts){
  tbody.innerHTML = "";
  for (const a of acts){
    const tr = document.createElement("tr");

    const cells = [
      {t: fmtDate(a.start_date)},
      {t: a.name || ""},
      {t: a.distance_km ? fmt(a.distance_km,2) : "", cls:"num"},
      {t: a.avg_pace_min_per_km ? fmt(a.avg_pace_min_per_km,2) : "", cls:"num"},
      {t: a.avg_heartrate ? fmt(a.avg_heartrate,0) : "", cls:"num"},
      {t: a.efficiency_factor ? fmt(a.efficiency_factor,2) : "", cls:"num"},
    ];
    for (const c of cells){
      const td = document.createElement("td");
      td.textContent = c.t;
      if (c.cls) td.className = c.cls;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function renderEFPlot(metrics){
  const m = metrics
    .filter(x => x.efficiency_factor !== null && x.start_date)
    .sort((a,b)=>new Date(a.start_date)-new Date(b.start_date));

  const x = m.map(d => d.start_date);
  const y = m.map(d => d.efficiency_factor);

  Plotly.newPlot("ef_plot", [{
    x, y,
    mode:"lines+markers",
    type:"scatter",
    marker:{size:6, color:"#4da3ff"},
    line:{width:2, color:"#4da3ff"}
  }], {
    margin:{l:55,r:20,t:10,b:45},
    paper_bgcolor:"rgba(0,0,0,0)",
    plot_bgcolor:"rgba(0,0,0,0)",
    font:{color:"#e9eef7"},
    xaxis:{title:"Date", gridcolor:"rgba(255,255,255,.06)"},
    yaxis:{title:"Efficiency Factor (m per bpm)", gridcolor:"rgba(255,255,255,.06)"}
  }, {displayModeBar:false});
}

function renderPMCPlot(pmc){
  if (!pmc.length){
    Plotly.newPlot("pmc_plot", [], {paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)"}, {displayModeBar:false});
    return;
  }
  const x = pmc.map(d => d.day);
  const ctl = pmc.map(d => d.ctl);
  const atl = pmc.map(d => d.atl);
  const tsb = pmc.map(d => d.tsb);

  Plotly.newPlot("pmc_plot", [
    {x, y: ctl, mode:"lines", name:"CTL (Fitness)", line:{color:"#34d399", width:2}},
    {x, y: atl, mode:"lines", name:"ATL (Fatigue)", line:{color:"#fbbf24", width:2}},
    {x, y: tsb, mode:"lines", name:"TSB (Form)", line:{color:"#4da3ff", width:2}},
  ], {
    margin:{l:55,r:20,t:10,b:45},
    paper_bgcolor:"rgba(0,0,0,0)",
    plot_bgcolor:"rgba(0,0,0,0)",
    font:{color:"#e9eef7"},
    xaxis:{title:"Date", gridcolor:"rgba(255,255,255,.06)"},
    yaxis:{title:"Score", gridcolor:"rgba(255,255,255,.06)"},
    legend:{orientation:"h", y:-0.25}
  }, {displayModeBar:false});
}

function renderStatus(s){
  if (!s || s.status !== "ok" || s.ctl === undefined){
    ctlVal.textContent = "–"; atlVal.textContent="–"; tsbVal.textContent="–";
    ctlDelta.textContent = "Call /pmc/recompute"; atlDelta.textContent=""; tsbDelta.textContent="";
    return;
  }
  ctlVal.textContent = fmt(s.ctl,1);
  atlVal.textContent = fmt(s.atl,1);
  tsbVal.textContent = fmt(s.tsb,1);

  ctlDelta.textContent = s.delta7_ctl !== null ? `7d: ${fmt(s.delta7_ctl,1)}` : "7d: –";
  atlDelta.textContent = s.delta7_atl !== null ? `7d: ${fmt(s.delta7_atl,1)}` : "7d: –";
  tsbDelta.textContent = s.delta7_tsb !== null ? `7d: ${fmt(s.delta7_tsb,1)}` : "7d: –";
}

async function main(){
  setStatus("Loading…");

  // Always recompute per-activity metrics (cheap at your scale)
  await recomputeMetrics();

  // Ensure PMC exists; if not, recompute once
  const status0 = await getStatus();
  if (status0.note && status0.note.includes("No PMC")) await recomputePMC();

  const [acts, series, pmc, status] = await Promise.all([
    getActivities(),
    getMetricsSeries(),
    getPMC(160),
    getStatus()
  ]);

  renderTable(acts);
  renderEFPlot(series);
  renderPMCPlot(pmc);
  renderStatus(status);

  setStatus(`Loaded ${acts.length} activities`);
}

btnMetrics.addEventListener("click", async () => {
  await recomputeMetrics();
  const acts = await getActivities();
  const series = await getMetricsSeries();
  renderTable(acts);
  renderEFPlot(series);
  setStatus(`Loaded ${acts.length} activities`);
});

btnPMC.addEventListener("click", async () => {
  await recomputePMC();
  const pmc = await getPMC(160);
  const status = await getStatus();
  renderPMCPlot(pmc);
  renderStatus(status);
});

main().catch(err => {
  console.error(err);
  setStatus("Error (see console)");
});
