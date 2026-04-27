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

// --------- shared dark layout for Plotly ----------
const DARK_LAYOUT = {
  paper_bgcolor: "#121622",
  plot_bgcolor: "#121622",
  font: { color: "#e8ecf3" },
  xaxis: { gridcolor: "#20263a", zerolinecolor: "#20263a" },
  yaxis: { gridcolor: "#20263a", zerolinecolor: "#20263a" },
  legend: { orientation: "h" },
  margin: { t: 20, r: 15, l: 55, b: 45 }
};

// --------- replace scenario bar with table + line plot ----------
async function scenarios(){
  const d = await j(`${API}/api/scenarios?days=14`);
  const s = d.scenarios.slice(0,3); // already ranked

  // --- table (primary) ---
  const rows = s.map(o => `
    <tr>
      <td><strong>${o.name}</strong></td>
      <td class="num">${o.delta_ctl.toFixed(1)}</td>
      <td class="num">${o.delta_atl.toFixed(1)}</td>
      <td class="num">${o.delta_tsb.toFixed(1)}</td>
      <td>${o.recommendation === "good" ? "✅ sensible" : "⚠️ risky"}</td>
    </tr>
  `).join("");

  document.getElementById("scenario_meta").innerHTML = `
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr>
          <th>Option</th>
          <th class="num">ΔFitness</th>
          <th class="num">ΔFatigue</th>
          <th class="num">ΔForm</th>
          <th>Assessment</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="small" style="margin-top:6px">
      <strong>Fitness (CTL)</strong> = long‑term load · 
      <strong>Fatigue (ATL)</strong> = short‑term load · 
      <strong>Form (TSB)</strong> = CTL − ATL
    </p>
  `;

  // --- line plot (secondary) ---
  const N = s[0].series.tsb.length;
  const x = Array.from({length:N}, (_,i)=> i+1);

  const traces = s.map(o => ({
    x,
    y:o.series.tsb,
    type:"scatter",
    mode:"lines",
    name:o.name,
    line:{width:2}
  }));

  Plotly.newPlot("scenario_bar", traces, {
    ...DARK_LAYOUT,
    xaxis:{ title:"days ahead" },
    yaxis:{ title:"Form (TSB)" }
  }, {responsive:true});
}

// --------- weekly zone status summary ----------
function zoneStatus(zones){
  const z = zones;
  const frac = k => z[k] ? z[k].fraction : 0;

  const aero = Math.max(frac("Z1"), frac("Z2"));
  const tempo = frac("Z3");
  const hard = Math.max(frac("Z4"), frac("Z5"));

  const level = f =>
    f > 1.1 ? "high ⚠️" :
    f >= 0.7 ? "on target ✅" :
    "low ⏸️";

  return `
    This week:
    • Aerobic base (Z1–Z2): ${level(aero)}
    • Tempo stress (Z3): ${level(tempo)}
    • High intensity (Z4–Z5): ${level(hard)}
  `;
}

// plug into existing zoneEffort render
const _zoneEffort = zoneEffort;
zoneEffort = async function(){
  const d = await j(`${API}/api/zone_effort?weeks=1`);
  if(d.status !== "ok") return;

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

  document.getElementById("zone_effort_meta").innerText =
    zones.map(z=>`${z}: ${d.zones[z].minutes} min`).join(" · ");

  // NEW: add coaching-style summary just below
  const summary = zoneStatus(d.zones);
  const p = document.createElement("pre");
  p.style.marginTop = "6px";
  p.style.color = "#9aa3c7";
  p.style.fontSize = "0.95rem";
  p.textContent = summary;
  document.getElementById("zone_effort_meta").appendChild(p);
};

// --------- auto-tune zone targets from CTL trend ----------
function inferPhaseFromCTL(series){
  if(series.length < 28) return {phase:"unknown", factor:1.0};

  const recent = series.slice(-7).map(d => d.ctl);
  const earlier = series.slice(-28,-21).map(d => d.ctl);

  const rAvg = recent.reduce((a,b)=>a+b,0)/recent.length;
  const eAvg = earlier.reduce((a,b)=>a+b,0)/earlier.length;
  const delta = rAvg - eAvg;

  if(delta > 2) return {phase:"base/build", factor:1.15};
  if(delta < -2) return {phase:"recovery", factor:0.85};
  return {phase:"maintenance", factor:1.0};
}

// override zoneEffort to apply adaptive targets
const _zoneEffortAuto = zoneEffort;
zoneEffort = async function(){
  const d = await j(`${API}/api/zone_effort?weeks=1`);
  const l = await j(`${API}/api/load?days=42`);
  if(d.status !== "ok" || !l.series) return;

  const { phase, factor } = inferPhaseFromCTL(l.series);

  const zones = Object.keys(d.zones);
  const minutes = [];
  const frac = [];
  const labels = [];

  zones.forEach(z => {
    const baseGoal = d.zones[z].goal;
    const adjGoal =
      (z === "Z2") ? baseGoal * factor :
      (z === "Z3") ? baseGoal / factor :
      baseGoal;

    const m = d.zones[z].minutes;
    const f = adjGoal ? m / adjGoal : 0;

    minutes.push(m);
    frac.push(Math.round(f*100));
    labels.push(`${Math.round(f*100)}%`);
  });

  Plotly.newPlot("zone_effort", [{
    x: minutes,
    y: zones,
    orientation: "h",
    type: "bar",
    text: labels,
    textposition: "outside",
    marker:{color:["#4da3ff","#3ddc97","#ffcc66","#ff6b6b","#ff4dff"]}
  }], {margin:{l:40,r:20,t:10,b:30}, paper_bgcolor:"#121622"});

  document.getElementById("zone_effort_meta").innerText =
    `Targets auto‑adjusted for ${phase} phase (CTL‑based).`;
};
