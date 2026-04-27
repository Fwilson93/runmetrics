const API = "https://runmetrics.onrender.com";
document.getElementById("api_url").textContent = API;

function fmtDate(iso){
  if(!iso) return "";
  const d = new Date(iso);
  return d.toISOString().slice(0,10);
}
function fmt(x, dp=1){
  if(x === null || x === undefined || Number.isNaN(Number(x))) return "";
  return Number(x).toFixed(dp);
}
function paceMmSs(minPerKm){
  if(minPerKm === null || minPerKm === undefined) return "";
  const totalSec = Math.round(minPerKm * 60);
  const mm = Math.floor(totalSec/60);
  const ss = totalSec % 60;
  return `${mm}:${ss.toString().padStart(2,"0")}`;
}
async function fetchJSON(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

const PLOTLY_LAYOUT_COMMON = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#e9eef6" },
  xaxis: { gridcolor: "#1f2430", zerolinecolor: "#1f2430" },
  yaxis: { gridcolor: "#1f2430", zerolinecolor: "#1f2430" },
  legend: { orientation: "h" },
  margin: { t: 20, r: 10, l: 55, b: 55 }
};

async function renderWeekly(){
  const data = await fetchJSON(`${API}/api/weekly?weeks=16`);
  const weeks = data.weeks || [];
  const x = weeks.map(w => w.week_start);
  const y = weeks.map(w => w.distance_km);
  const goal = weeks.length ? weeks[0].goal_km : null;
  const goalLine = weeks.map(_ => goal);

  Plotly.newPlot("weekly_plot", [
    { x, y, type:"bar", name:"km", marker:{color:"#6aa9ff"} },
    { x, y:goalLine, type:"scatter", mode:"lines", name:"goal", line:{dash:"dot", color:"#ffcc66"} }
  ], {
    ...PLOTLY_LAYOUT_COMMON,
    yaxis: { ...PLOTLY_LAYOUT_COMMON.yaxis, title:"km" },
    xaxis: { ...PLOTLY_LAYOUT_COMMON.xaxis, tickangle:-35, title:"week start (Mon)" }
  }, {responsive:true});

  document.getElementById("weekly_meta").textContent =
    `Goal = ${goal} km/week (${data.goal_source}).`;
}

async function renderLoad(){
  const data = await fetchJSON(`${API}/api/load?days=140`);
  const s = data.series || [];
  const x = s.map(p => p.date);
  const ctl = s.map(p => p.ctl);
  const atl = s.map(p => p.atl);
  const tsb = s.map(p => p.tsb);

  Plotly.newPlot("load_plot", [
    { x, y:ctl, type:"scatter", mode:"lines", name:"CTL", line:{color:"#6aa9ff"} },
    { x, y:atl, type:"scatter", mode:"lines", name:"ATL", line:{color:"#ff6b6b"} },
    { x, y:tsb, type:"scatter", mode:"lines", name:"TSB", line:{dash:"dot", color:"#3ddc97"} },
  ], {
    ...PLOTLY_LAYOUT_COMMON,
    yaxis: { ...PLOTLY_LAYOUT_COMMON.yaxis, title:"load units" },
    xaxis: { ...PLOTLY_LAYOUT_COMMON.xaxis, title:"date" }
  }, {responsive:true});

  document.getElementById("load_meta").textContent =
    `HRmax observed ~${fmt(data.hrmax_observed,0)} bpm; missing-HR sessions in window=${data.hr_missing_sessions_in_window}; τCTL=${data.tau_ctl}, τATL=${data.tau_atl}.`;
}

async function renderRecent(){
  const data = await fetchJSON(`${API}/api/recent?limit=25`);
  const tbody = document.querySelector("#recent tbody");
  tbody.innerHTML = "";
  for(const it of (data.items || [])){
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

function scenarioBadge(rec){
  const c = rec === "good" ? "#3ddc97" : (rec === "risky" ? "#ff6b6b" : "#ffcc66");
  return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid ${c};color:${c};margin-left:6px">${rec}</span>`;
}

async function renderScenarios(){
  const data = await fetchJSON(`${API}/api/scenarios?days=14`);
  const all = data.scenarios || [];
  const top = all.slice(0,3); // ranked already by backend

  // x axis = day 1..N
  const N = top.length ? top[0].series.tsb.length : 0;
  const x = Array.from({length:N}, (_,i)=> `D+${i+1}`);

  const traces = top.map((s, idx) => ({
    x,
    y: s.series.tsb,
    type: "scatter",
    mode: "lines",
    name: `${s.name}`,
    line: { width: 3 }
  }));

  Plotly.newPlot("scenario_plot", traces, {
    ...PLOTLY_LAYOUT_COMMON,
    yaxis: { ...PLOTLY_LAYOUT_COMMON.yaxis, title:"TSB (form)" },
    xaxis: { ...PLOTLY_LAYOUT_COMMON.xaxis, title:"projection horizon" }
  }, {responsive:true});

  // small table summary
  const rows = top.map(s => `
    <tr>
      <td><strong>${s.name}</strong>${scenarioBadge(s.recommendation)}</td>
      <td class="num">${fmt(s.delta_ctl,1)}</td>
      <td class="num">${fmt(s.delta_atl,1)}</td>
      <td class="num">${fmt(s.delta_tsb,1)}</td>
    </tr>
  `).join("");

  document.getElementById("scenario_table").innerHTML = `
    <div style="margin-top:8px;overflow-x:auto">
      <table style="min-width:520px">
        <thead>
          <tr>
            <th>Option</th>
            <th class="num">ΔCTL</th>
            <th class="num">ΔATL</th>
            <th class="num">ΔTSB</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

async function renderZones(){
  const data = await fetchJSON(`${API}/api/zones`);
  if(data.status !== "ok"){
    document.getElementById("zones_meta").textContent = "Not enough data yet to estimate zones reliably.";
    return;
  }

  const hrmax = data.hrmax;
  const lt1 = data.lt1_hr;
  const lt2 = data.lt2_hr;

  // Build zone bands as horizontal shapes on x-axis (HR)
  // We'll plot a dummy scatter so Plotly renders axes.
  const shapes = [];
  const zoneOrder = ["Z1","Z2","Z3","Z4","Z5"];
  const colors = {
    Z1:"#4da3ff33",
    Z2:"#3ddc9733",
    Z3:"#ffcc6633",
    Z4:"#ff6b6b33",
    Z5:"#ff4dff26"
  };

  zoneOrder.forEach((z, i) => {
    const [lo, hi] = data.zones[z];
    shapes.push({
      type:"rect",
      xref:"x",
      yref:"paper",
      x0: lo,
      x1: hi,
      y0: 0,
      y1: 1,
      fillcolor: colors[z],
      line: {width:0}
    });
  });

  // markers for LT1/LT2/HRmax
  const markerLines = [lt1, lt2, hrmax].map((xv, i) => ({
    type:"line",
    xref:"x", yref:"paper",
    x0:xv, x1:xv, y0:0, y1:1,
    line:{color:"#e9eef6", width:2, dash: i===2 ? "dot" : "dash"}
  }));

  Plotly.newPlot("zones_plot", [{
    x: [0, hrmax],
    y: [0, 0],
    mode:"lines",
    line:{color:"rgba(0,0,0,0)"},
    showlegend:false
  }], {
    ...PLOTLY_LAYOUT_COMMON,
    shapes: [...shapes, ...markerLines],
    xaxis: { ...PLOTLY_LAYOUT_COMMON.xaxis, title:"Heart rate (bpm)", range:[Math.max(80, 0.55*hrmax), hrmax+5] },
    yaxis: { visible:false },
    margin: { t: 20, r: 10, l: 30, b: 45 },
  }, {responsive:true});

  document.getElementById("zones_meta").textContent =
    `HRmax(observed)≈${hrmax} bpm • LT1≈${lt1} bpm • LT2≈${lt2} bpm (estimates).`;
}

(async function main(){
  try{
    await renderWeekly();
    await renderLoad();
    await renderScenarios();
    await renderZones();
    await renderRecent();
  }catch(e){
    console.error(e);
    alert("Dashboard couldn't load API data. If Render was sleeping, refresh the page.");
  }
})();
