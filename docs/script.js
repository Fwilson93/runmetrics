const API = "https://runmetrics.onrender.com";

const paceMmSs = v => {
  if (v == null) return "";
  const s = Math.round(v * 60);
  return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
};

async function j(url){ const r = await fetch(url); return r.json(); }

async function zoneEffort(){
  const d = await j(`${API}/api/zone_effort?weeks=1`);
  if (d.status !== "ok") return;

  const zones = Object.keys(d.zones);
  const mins = zones.map(z => d.zones[z].minutes);
  const frac = zones.map(z => Math.round(100*d.zones[z].fraction));

  Plotly.newPlot("zone_effort", [{
    x: mins,
    y: zones,
    orientation: "h",
    type: "bar",
    text: frac.map(f=>`${f}%`),
    textposition: "outside",
    marker:{color:["#4da3ff","#3ddc97","#ffcc66","#ff6b6b","#ff4dff"]}
  }], {margin:{l:40,r:20,t:10,b:30}});
  
  document.getElementById("zone_effort_meta").textContent =
    zones.map(z=>`${z}: ${d.zones[z].minutes} min`).join(" · ");
}

async function loadBar(){
  const d = await j(`${API}/api/load?days=14`);
  const last = d.series.at(-1);

  Plotly.newPlot("load_bar", [{
    x:["Fitness","Fatigue","Form"],
    y:[last.ctl,last.atl,last.tsb],
    type:"bar",
    marker:{color:["#4da3ff","#ff6b6b","#3ddc97"]}
  }], {margin:{l:40,r:10,t:10,b:30}});
}

async function scenarios(){
  const d = await j(`${API}/api/scenarios?days=14`);
  const s = d.scenarios.slice(0,3);

  Plotly.newPlot("scenario_bar", [{
    x: s.map(o=>o.name),
    y: s.map(o=>o.delta_tsb),
    type:"bar",
    marker:{color:["#3ddc97","#ffcc66","#ff6b6b"]}
  }], {margin:{l:40,r:10,t:10,b:40}});

  document.getElementById("scenario_meta").textContent =
    "Higher bar = better improvement in Form over 14 days.";
}

async function recent(){
  const d = await j(`${API}/api/recent?limit=10`);
  const tb = document.querySelector("#recent tbody");
  tb.innerHTML="";
  d.items.forEach(a=>{
    tb.innerHTML+=`<tr>
      <td>${a.date?.slice(0,10)||""}</td>
      <td>${a.name||""}</td>
      <td>${a.distance_km?.toFixed(1)||""}</td>
      <td>${paceMmSs(a.pace_min_per_km)}</td>
      <td>${a.avg_hr||""}</td>
    </tr>`;
  });
}

zoneEffort(); loadBar(); scenarios(); recent();
