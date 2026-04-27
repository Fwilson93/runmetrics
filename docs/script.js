/* RUNMETRICS_DARK_THEME: enforce dark Plotly theme */
const RUNMETRICS_PLOTLY_DARK = {
  paper_bgcolor: "#0f1117",
  plot_bgcolor: "#0f1117",
  font: { color: "#e9eef6" },
  xaxis: { gridcolor: "#1f2430", zerolinecolor: "#1f2430" },
  yaxis: { gridcolor: "#1f2430", zerolinecolor: "#1f2430" },
  legend: { orientation: "h" },
  margin: { t: 20, r: 10, l: 60, b: 45 }
};
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
function recBadge(rec){
  const c = rec==="good" ? "#3ddc97" : (rec==="caution" ? "#ffcc66" : "#ff6b6b");
  const t = rec==="good" ? "✅ sensible" : (rec==="caution" ? "⚠️ caution" : "⛔ risky");
  return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid ${c};color:${c}">${t}</span>`;
}

const DARK = {
  paper_bgcolor:"#121622",
  plot_bgcolor:"#121622",
  font:{color:"#e8ecf3"},
  xaxis:{gridcolor:"#20263a",zerolinecolor:"#20263a"},
  yaxis:{gridcolor:"#20263a",zerolinecolor:"#20263a"},
  legend:{orientation:"h"},
  margin:{t:20,r:10,l:60,b:45},
};

function nextDates(n){
  const out = [];
  const now = new Date();
  // start tomorrow (UTC date strings)
  for(let i=1;i<=n;i++){
    const d = new Date(now.getTime() + i*24*3600*1000);
    out.push(d.toISOString().slice(0,10));
  }
  return out;
}

async function renderScenarioTable(data){
  const s = (data.scenarios || []).slice(0,3);
  const rows = s.map(o => `
    <tr>
      <td><strong>${o.name}</strong></td>
      <td class="num">${fmt(o.delta_ctl,1)}</td>
      <td class="num">${fmt(o.delta_atl,1)}</td>
      <td class="num">${fmt(o.delta_tsb,1)}</td>
      <td>${recBadge(o.recommendation)}</td>
    </tr>
  `).join("");

  document.getElementById("scenario_table").innerHTML = `
    <div class="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Option</th>
            <th class="num">ΔFitness (CTL)</th>
            <th class="num">ΔFatigue (ATL)</th>
            <th class="num">ΔForm (TSB)</th>
            <th>Assessment</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="small muted" style="margin-top:8px">
      <strong>CTL</strong>=Fitness · <strong>ATL</strong>=Fatigue · <strong>TSB</strong>=Form=CTL−ATL
    </p>
  `;
}

function findScenario(data, predicate){
  const arr = data.scenarios || [];
  return arr.find(predicate) || null;
}

async function renderLoadWithProjections(){
  // controls
  const dur = Number(document.getElementById("dur").value);
  const intensity = Number(document.getElementById("intensity_mode").value);
  document.getElementById("dur_lbl").textContent = dur;

  const intLabel = document.getElementById("intensity_mode").selectedOptions[0].textContent;
  // show percent in text if you like:
  document.getElementById("int_lbl")?.remove?.(); // ignore if not present

  // Fetch history
  const hist = await fetchJSON(`${API}/api/load?days=140`);
  const series = hist.series || [];
  const xPast = series.map(p => p.date);

  const ctlPast = series.map(p => p.ctl);
  const atlPast = series.map(p => p.atl);
  const tsbPast = series.map(p => p.tsb);

  // Fetch scenarios for 7-day projection
  const scen = await fetchJSON(`${API}/api/scenarios_dynamic?days=7&dur_min=${dur}&intensity=${intensity}`);

  if(scen.status !== "ok"){
    // just plot history
    Plotly.newPlot("load_plot", [
      {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL)",line:{color:"#6aa9ff"}},
      {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL)",line:{color:"#ff6b6b"}},
      {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB)",line:{color:"#3ddc97",dash:"dot"}},
    ], {...DARK, yaxis:{...DARK.yaxis,title:"load units"}, xaxis:{...DARK.xaxis,title:"date"}}, {responsive:true});
    return;
  }

  await renderScenarioTable(scen);

  const recommended = scen.scenarios[0];
  const rest = findScenario(scen, s => s.name === "Rest") || scen.scenarios[1];
  const custom = findScenario(scen, s => s.name.startsWith("Custom:")) || scen.scenarios[0];

  const xFut = nextDates(7);

  // Styling rules per scenario
  const styles = [
    { key:"rest", label:"Rest", dash:"dot", width:2, opacity:0.75, scen:rest },
    { key:"rec", label:"Recommended", dash:"dash", width:2.5, opacity:0.85, scen:recommended },
    { key:"custom", label:`Your choice (${dur}min, ${intLabel})`, dash:"dashdot", width:1.5, opacity:0.70, scen:custom },
  ];

  // metric colours
  const C = { ctl:"#6aa9ff", atl:"#ff6b6b", tsb:"#3ddc97" };

  const traces = [
    {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL) past",line:{color:C.ctl,width:3}},
    {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL) past",line:{color:C.atl,width:3}},
    {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB) past",line:{color:C.tsb,width:3}},
  ];

  // add projections for each metric/scenario
  for(const st of styles){
    const s = st.scen.series;
    traces.push({
      x:xFut, y:s.ctl, type:"scatter", mode:"lines",
      name:`CTL ${st.label}`, line:{color:C.ctl, dash:st.dash, width:st.width}, opacity:st.opacity
    });
    traces.push({
      x:xFut, y:s.atl, type:"scatter", mode:"lines",
      name:`ATL ${st.label}`, line:{color:C.atl, dash:st.dash, width:st.width}, opacity:st.opacity
    });
    traces.push({
      x:xFut, y:s.tsb, type:"scatter", mode:"lines",
      name:`TSB ${st.label}`, line:{color:C.tsb, dash:st.dash, width:st.width}, opacity:st.opacity
    });
  }

  Plotly.newPlot("load_plot", traces, {
    ...DARK,
    yaxis:{...DARK.yaxis,title:"load units"},
    xaxis:{...DARK.xaxis,title:"date"},
  }, {responsive:true});

  document.getElementById("load_meta").textContent =
    `HRmax observed ~${fmt(hist.hrmax_observed,0)} bpm · projections: dotted=rest, dashed=recommended, dash-dot=your choice`;
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
