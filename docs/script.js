const API = "https://runmetrics.onrender.com";

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toISOString().slice(0,10);
}

function fmt(x, dp=1) {
  if (x === null || x === undefined) return "";
  return Number(x).toFixed(dp);
}

function paceMmSs(minPerKm) {
  if (minPerKm === null || minPerKm === undefined) return "";
  const totalSec = Math.round(minPerKm * 60);
  const mm = Math.floor(totalSec / 60);
  const ss = totalSec % 60;
  return `${mm}:${ss.toString().padStart(2, "0")}`;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function renderWeekly() {
  const data = await fetchJSON(`${API}/api/weekly?weeks=16`);
  const weeks = data.weeks || [];
  const x = weeks.map(w => w.week_start);
  const y = weeks.map(w => w.distance_km);
  const goal = weeks.length ? weeks[0].goal_km : null;
  const goalLine = weeks.map(_ => goal);

  Plotly.newPlot("weekly_plot", [
    { x, y, type: "bar", name: "Distance (km)" },
    { x, y: goalLine, type: "scatter", mode: "lines", name: "Goal", line: { dash: "dot" } }
  ], {
    margin: { t: 20, r: 10, l: 50, b: 60 },
    yaxis: { title: "km" },
    xaxis: { title: "Week start (Mon)", tickangle: -35 },
    legend: { orientation: "h" }
  }, {responsive: true});

  document.getElementById("weekly_meta").textContent =
    `Goal = ${goal} km/week (${data.goal_source}).`;
}

async function renderLoad() {
  const data = await fetchJSON(`${API}/api/load?days=140`);
  const s = data.series || [];
  const x = s.map(p => p.date);
  const ctl = s.map(p => p.ctl);
  const atl = s.map(p => p.atl);
  const tsb = s.map(p => p.tsb);

  Plotly.newPlot("load_plot", [
    { x, y: ctl, type: "scatter", mode: "lines", name: "CTL (fitness)" },
    { x, y: atl, type: "scatter", mode: "lines", name: "ATL (fatigue)" },
    { x, y: tsb, type: "scatter", mode: "lines", name: "TSB (form)", line: { dash: "dot" } }
  ], {
    margin: { t: 20, r: 10, l: 60, b: 40 },
    yaxis: { title: "Load units" },
    xaxis: { title: "Date" },
    legend: { orientation: "h" }
  }, {responsive: true});

  document.getElementById("load_meta").textContent =
    `HRmax observed=${fmt(data.hrmax_observed,0)} bpm; HR-missing sessions in window=${data.hr_missing_sessions_in_window}.`;
}

async function renderRecent() {
  const data = await fetchJSON(`${API}/api/recent?limit=25`);
  const tbody = document.querySelector("#recent tbody");
  tbody.innerHTML = "";
  for (const it of data.items || []) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtDate(it.date)}</td>
      <td>${it.name || ""}</td>
      <td>${it.sport_type || ""}</td>
      <td class="num">${it.distance_km ? fmt(it.distance_km,1) : ""}</td>
      <td class="num">${paceMmSs(it.pace_min_per_km)}</td>
      <td class="num">${it.avg_hr ? fmt(it.avg_hr,0) : ""}</td>
      <td class="num">${it.ef ? fmt(it.ef,0) : ""}</td>
    `;
    tbody.appendChild(tr);
  }
}

(async function main() {
  await renderWeekly();
  await renderLoad();
  await renderRecent();
})();
