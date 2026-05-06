/* RunMetrics – static GitHub Pages renderer
 *
 * Data sources:
 *   docs/data/load_365.json
 *   docs/data/recent.json
 */

const BASE = window.location.origin + window.location.pathname.replace(/\/$/, "");
const DATA = BASE + "/data";

/* ---------- utilities ---------- */

async function fetchJSON(path){
  const r = await fetch(path, { cache: "no-store" });
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}: ${path}`);
  return r.json();
}

function fmt(x, dp = 1){
  if(x === null || x === undefined || Number.isNaN(Number(x))) return "–";
  return Number(x).toFixed(dp);
}

function sliceLast(arr, n){
  if(!arr) return [];
  if(arr.length <= n) return arr;
  return arr.slice(arr.length - n);
}

/* ---------- plot CTL / ATL / TSB ---------- */

function plotLoad(series, generated_at){
  const plotDiv = document.getElementById("load_plot");
  const metaDiv = document.getElementById("load_meta");
  if(!plotDiv) return;

  const s = sliceLast(series, 120);

  const x   = s.map(p => p.date);
  const ctl = s.map(p => p.ctl);
  const atl = s.map(p => p.atl);
  const tsb = s.map(p => p.tsb);

  const layout = {
    paper_bgcolor:"#0f1117",
    plot_bgcolor:"#0f1117",
    font:{color:"#e9eef6"},
    xaxis:{gridcolor:"#1f2430"},
    yaxis:{gridcolor:"#1f2430", title:"load"},
    margin:{t:20,l:55,r:10,b:45},
    legend:{orientation:"h"}
  };

  const traces = [
    {x, y:ctl, name:"CTL (fitness)", mode:"lines", line:{color:"#6aa9ff", width:3}},
    {x, y:atl, name:"ATL (fatigue)", mode:"lines", line:{color:"#ff6b6b", width:3}},
    {x, y:tsb, name:"TSB (form)",    mode:"lines", line:{color:"#3ddc97", width:3}},
  ];

  Plotly.newPlot(plotDiv, traces, layout, {displayModeBar:false});

  if(metaDiv){
    const last = s[s.length - 1];
    metaDiv.textContent =
      `Last update: ${generated_at.slice(0,19).replace("T"," ")} UTC · ` +
      `CTL ${fmt(last.ctl,1)} · ATL ${fmt(last.atl,1)} · TSB ${fmt(last.tsb,1)}`;
  }
}

/* ---------- recent activities list ---------- */

function renderRecent(items){
  const el = document.getElementById("recent_list");
  if(!el) return;

  el.innerHTML = items.map(a => {
    const d = (a.date || "").slice(0,10);
    const hr = (a.avg_hr === null || a.avg_hr === undefined) ? "–" : a.avg_hr;
    return `
      <div style="margin-bottom:6px">
        <strong>${d}</strong> — ${a.name}
        <span class="muted">
          (${fmt(a.distance_km,1)} km,
           ${fmt(a.pace_min_per_km,2)} min/km,
           HR ${hr})
        </span>
      </div>
    `;
  }).join("");
}

/* ---------- bootstrap ---------- */

async function render(){
  const load365 = await fetchJSON(`${DATA}/load_365.json`);
  if(load365.series && load365.series.length){
    plotLoad(load365.series, load365.generated_at);
  }

  const recent = await fetchJSON(`${DATA}/recent.json`);
  if(recent.items && recent.items.length){
    renderRecent(recent.items);
  }
}

document.addEventListener("DOMContentLoaded", () => {
 
