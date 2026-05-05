/* RunMetrics – static GitHub Pages loader (cache-busted) */

const BASE = window.location.origin + window.location.pathname.replace(/\/$/, "");
const DATA = BASE + "/data";

async function fetchJSON(path){
  const r = await fetch(path, { cache: "no-store" });
  if(!r.ok) throw new Error(`${r.status} ${r.statusText} ${path}`);
  return r.json();
}

function fmt(x, dp=1){
  if(x === null || x === undefined || Number.isNaN(Number(x))) return "";
  return Number(x).toFixed(dp);
}

async function render(){
  const recent = await fetchJSON(`${DATA}/recent.json`);

  const list = document.getElementById("recent_list");
  if(list){
    list.innerHTML = recent.items.map(a => {
      const d = (a.date || "").slice(0,10);
      return `<div class="small">
        <strong>${d}</strong> — ${a.name}
        <span class="muted">
          (${fmt(a.distance_km,1)} km, ${fmt(a.pace_min_per_km,2)} min/km, HR ${a.avg_hr ?? "–"})
        </span>
      </div>`;
    }).join("");
  }

  const hist = await fetchJSON(`${DATA}/load_365.json`);
  const last = hist.series[hist.series.length - 1];

  const meta = document.getElementById("load_meta");
  if(meta){
    meta.textContent =
      `Last update: ${hist.generated_at.slice(0,19).replace("T"," ")} UTC · ` +
      `CTL ${fmt(last.ctl,1)} ATL ${fmt(last.atl,1)} TSB ${fmt(last.tsb,1)}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  render().catch(err => {
    console.error(err);
    alert("RunMetrics data failed to load — see console.");
  });
});
