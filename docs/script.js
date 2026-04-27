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

const DARK = {
  paper_bgcolor:"#0f1117",
  plot_bgcolor:"#0f1117",
  font:{color:"#e9eef6"},
  xaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
  yaxis:{gridcolor:"#1f2430",zerolinecolor:"#1f2430"},
  legend:{orientation:"h"},
  margin:{t:20,r:10,l:60,b:45},
};

const C = { ctl:"#6aa9ff", atl:"#ff6b6b", tsb:"#3ddc97" };

function nextDatesFrom(lastIsoDate, n){
  // lastIsoDate: YYYY-MM-DD
  const base = new Date(lastIsoDate + "T00:00:00Z");
  const out = [];
  for(let i=1;i<=n;i++){
    const d = new Date(base.getTime() + i*24*3600*1000);
    out.push(d.toISOString().slice(0,10));
  }
  return out;
}

function recBadge(rec){
  const c = rec==="good" ? "#3ddc97" : (rec==="caution" ? "#ffcc66" : "#ff6b6b");
  const t = rec==="good" ? "✅ sensible" : (rec==="caution" ? "⚠️ caution" : "⛔ risky");
  return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid ${c};color:${c}">${t}</span>`;
}

function arrowFor(v){
  if(v > 1.0) return "↑";
  if(v < -1.0) return "↓";
  return "↔";
}
function fatigueText(v){
  // positive delta ATL = more fatigue; negative = less fatigue
  if(v > 1.0) return "more tired";
  if(v < -1.0) return "less tired";
  return "about the same";
}
function freshnessText(v){
  if(v > 1.0) return "fresher";
  if(v < -1.0) return "more tired";
  return "about the same";
}

async function renderScenarioTable(scen){
  const s = (scen.scenarios || []).slice(0,3);

  const rows = s.map(o => `
    <tr>
      <td><strong>${o.name}</strong></td>
      <td class="num">${arrowFor(o.delta_ctl)} <span class="muted">${fmt(o.delta_ctl,1)}</span></td>
      <td>${fatigueText(o.delta_atl)} <span class="muted">(${fmt(o.delta_atl,1)})</span></td>
      <td>${freshnessText(o.delta_tsb)} <span class="muted">(${fmt(o.delta_tsb,1)})</span></td>
      <td>${recBadge(o.recommendation)}</td>
    </tr>
  `).join("");

  document.getElementById("scenario_table").innerHTML = `
    <div class="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Option</th>
            <th class="num">Fitness change</th>
            <th>Fatigue change</th>
            <th>Freshness change</th>
            <th>Assessment</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="small muted" style="margin-top:8px">
      Fitness ≈ CTL (long-term load) · Fatigue ≈ ATL (short-term load) · Freshness ≈ TSB (CTL−ATL)
    </p>
  `;
}

async function renderLoadWithProjections(){
  const dur = Number(document.getElementById("dur").value);
  const intensity = Number(document.getElementById("intensity_mode").value);
  document.getElementById("dur_lbl").textContent = dur;

  // 1) past 90 days only
  const hist = await fetchJSON(`${API}/api/load?days=90`);
  const series = hist.series || [];
  const xPast = series.map(p => p.date);
  const ctlPast = series.map(p => p.ctl);
  const atlPast = series.map(p => p.atl);
  const tsbPast = series.map(p => p.tsb);

  const lastDate = xPast[xPast.length - 1];
  const lastCtl = ctlPast[ctlPast.length - 1];
  const lastAtl = atlPast[atlPast.length - 1];
  const lastTsb = tsbPast[tsbPast.length - 1];

  // 2) scenarios for next 7 days
  const scen = await fetchJSON(`${API}/api/scenarios_dynamic?days=7&dur_min=${dur}&intensity=${intensity}`);
  if(scen.status !== "ok"){
    Plotly.newPlot("load_plot", [
      {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL)",line:{color:C.ctl,width:3}},
      {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL)",line:{color:C.atl,width:3}},
      {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB)",line:{color:C.tsb,width:3,dash:"dot"}},
    ], {...DARK, yaxis:{...DARK.yaxis,title:"load units"}, xaxis:{...DARK.xaxis,title:"date"}}, {responsive:true});
    return;
  }

  await renderScenarioTable(scen);

  const recommended = scen.scenarios[0];
  const rest = (scen.scenarios || []).find(s => s.name === "Rest") || scen.scenarios[1];
  const custom = (scen.scenarios || []).find(s => s.name.startsWith("Custom:")) || scen.scenarios[0];

  // 3) Make projections continuous: start at last past point
  const xFut = nextDatesFrom(lastDate, 7);
  const xProj = [lastDate, ...xFut];

  function withStart(arr, startVal){
    return [startVal, ...arr];
  }

  const styles = [
    { label:"Rest", dash:"dot", width:2, opacity:0.70, scen:rest },
    { label:"Recommended", dash:"dash", width:2.5, opacity:0.85, scen:recommended },
    { label:"Your choice", dash:"dashdot", width:1.5, opacity:0.70, scen:custom },
  ];

  const traces = [
    {x:xPast,y:ctlPast,type:"scatter",mode:"lines",name:"Fitness (CTL) past",line:{color:C.ctl,width:3}},
    {x:xPast,y:atlPast,type:"scatter",mode:"lines",name:"Fatigue (ATL) past",line:{color:C.atl,width:3}},
    {x:xPast,y:tsbPast,type:"scatter",mode:"lines",name:"Form (TSB) past",line:{color:C.tsb,width:3,dash:"dot"}},
  ];

  for(const st of styles){
    const s = st.scen.series;

    traces.push({
      x:xProj, y:withStart(s.ctl, lastCtl),
      type:"scatter", mode:"lines",
      name:`CTL ${st.label}`, line:{color:C.ctl, dash:st.dash, width:st.width}, opacity:st.opacity
    });
    traces.push({
      x:xProj, y:withStart(s.atl, lastAtl),
      type:"scatter", mode:"lines",
      name:`ATL ${st.label}`, line:{color:C.atl, dash:st.dash, width:st.width}, opacity:st.opacity
    });
    traces.push({
      x:xProj, y:withStart(s.tsb, lastTsb),
      type:"scatter", mode:"lines",
      name:`TSB ${st.label}`, line:{color:C.tsb, dash:st.dash, width:st.width}, opacity:st.opacity
    });
  }

  Plotly.newPlot("load_plot", traces, {
    ...DARK,
    yaxis:{...DARK.yaxis,title:"load units"},
    xaxis:{...DARK.xaxis,title:"date"},
  }, {responsive:true});

  document.getElementById("load_meta").textContent =
    `Showing last 90 days. Projections (7d): dotted=rest, dashed=recommended, dash-dot=your choice.`;
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
