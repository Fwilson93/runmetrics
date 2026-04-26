const API = "https://runmetrics.onrender.com";

const statusEl = document.getElementById("status");
const btn = document.getElementById("recompute");
const tbody = document.querySelector("#activities tbody");

function setStatus(msg) { statusEl.textContent = msg; }

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toISOString().slice(0,10);
}

function fmtNum(x, digits=2) {
  if (x === null || x === undefined) return "";
  return Number(x).toFixed(digits);
}

async function recomputeMetrics() {
  setStatus("Recomputing metrics…");
  const r = await fetch(`${API}/metrics/derive`);
  const j = await r.json();
  setStatus(`Metrics: ${j.activities} activities (inserted ${j.inserted}, updated ${j.updated})`);
}

async function loadActivities() {
  setStatus("Loading activities…");
  const r = await fetch(`${API}/api/activities?limit=60`);
  const j = await r.json();
  if (!r.ok || j.status !== "ok") {
    setStatus("Failed to load activities");
    console.warn(j);
    return [];
  }
  setStatus(`Loaded ${j.count} activities`);
  return j.activities;
}

async function loadEFSeries() {
  const r = await fetch(`${API}/api/metrics?limit=300`);
  const j = await r.json();
  if (!r.ok || j.status !== "ok") {
    console.warn(j);
    return [];
  }
  return j.metrics;
}

function renderTable(activities) {
  tbody.innerHTML = "";
  for (const a of activities) {
    const tr = document.createElement("tr");

    const tds = [
      { text: fmtDate(a.start_date) },
      { text: a.name || "" },
      { text: fmtNum(a.distance_km, 2), cls: "num" },
      { text: a.avg_pace_min_per_km ? fmtNum(a.avg_pace_min_per_km, 2) : "", cls: "num" },
      { text: a.avg_heartrate ? fmtNum(a.avg_heartrate, 0) : "", cls: "num" },
      { text: a.efficiency_factor ? fmtNum(a.efficiency_factor, 2) : "", cls: "num" },
    ];

    for (const c of tds) {
      const td = document.createElement("td");
      td.textContent = c.text;
      if (c.cls) td.className = c.cls;
      tr.appendChild(td);
    }

    tbody.appendChild(tr);
  }
}

function renderEFPlot(metrics) {
  // sort oldest -> newest for nicer plots
  const m = metrics.slice().filter(x => x.efficiency_factor !== null && x.start_date).sort((a,b)=>new Date(a.start_date)-new Date(b.start_date));

  const x = m.map(d => d.start_date);
  const y = m.map(d => d.efficiency_factor);
  const text = m.map(d => `EF=${fmtNum(d.efficiency_factor,2)}<br>Pace=${d.avg_pace_min_per_km ? fmtNum(d.avg_pace_min_per_km,2) : "?"} min/km<br>HR=${d.avg_heartrate ? fmtNum(d.avg_heartrate,0) : "?"}`);

  Plotly.newPlot("ef_plot", [{
    x, y,
    mode: "markers+lines",
    type: "scatter",
    text,
    hoverinfo: "text+x",
    marker: { size: 7, color: "#0b62ff" },
    line: { width: 2, color: "#0b62ff" }
  }], {
    margin: { l: 50, r: 20, t: 10, b: 40 },
    xaxis: { title: "Date" },
    yaxis: { title: "Efficiency Factor (m per bpm)", zeroline: false },
  }, {displayModeBar: false});
}

async function main() {
  // recompute once per page load (cheap for your dataset)
  await recomputeMetrics();
  const activities = await loadActivities();
  renderTable(activities);
  const series = await loadEFSeries();
  renderEFPlot(series);
}

btn.addEventListener("click", async () => {
  await recomputeMetrics();
  const activities = await loadActivities();
  renderTable(activities);
  const series = await loadEFSeries();
  renderEFPlot(series);
});

main().catch(err => {
  console.error(err);
  setStatus("Error (see console)");
});
