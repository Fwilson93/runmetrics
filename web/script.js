const API = "https://runmetrics.onrender.com";

/**
 * Helpers
 */
const paceMinPerKm = (s) =>
  s ? (s / 60).toFixed(2) : "";

async function loadActivities() {
  const res = await fetch(`${API}/metrics/derive`);
  if (!res.ok) {
    console.warn("Metrics derive endpoint not reachable");
  }

  const activitiesRes = await fetch(`${API}/strava/ingest?after=2026-01-01`);
  await activitiesRes.json(); // ensure backend awake

  const dbRes = await fetch(`${API}/health`);
  if (!dbRes.ok) return;

  // ⚠️ Hacky but fine: no public list endpoint yet
  // We'll add one later
}

async function loadMetrics() {
  const res = await fetch(`${API}/metrics/derive`);
  if (!res.ok) return;

  const data = await res.json();
  console.log("Metrics recomputed:", data);

  // Pull activity metrics directly from DB via temporary shortcut:
  const rowsRes = await fetch(`${API}/strava/ingest?after=2026-01-01`);
  await rowsRes.json();
}

async function fetchSummary() {
  const res = await fetch(`${API}/metrics/derive`);
  await res.json();

  const raw = await fetch(`${API}/streams?fake=1`).catch(() => null);
}

async function renderEF() {
  // Temporary: use derived metrics table via dedicated query later
  // For now, this is a placeholder visual reward
  Plotly.newPlot("ef_plot", [{
    y: [],
    mode: "markers",
    type: "scatter"
  }], {
    xaxis: { title: "Activity" },
    yaxis: { title: "Efficiency Factor" },
  });
}

renderEF();
