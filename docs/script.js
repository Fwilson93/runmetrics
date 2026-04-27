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
  paper_bgcolor:"#121622",
  plot_bgcolor:"#121622",
  font:{color:"#e8ecf3"},
  xaxis:{gridcolor:"#20263a",zerolinecolor:"#20263a"},
  yaxis:{gridcolor:"#20263a",zerolinecolor:"#20263a"},
  legend:{orientation:"h"},
  margin:{t:20,r:10,l:60,b:45},
};

async function renderLongTermLoad(){
  const data = await fetchJSON(`${API}/api/load?days=140`);
  const s = data.series || [];
  const x = s.map(p=>p.date);
  const ctl = s.map(p=>p.ctl);
  const atl = s.map(p=>p.atl);
  const tsb = s.map(p=>p.tsb);

  Plotly.newPlot("load_plot", [
    {x,y:ctl,type:"scatter",mode:"lines",name:"Fitness (CTL)",line:{color:"#6aa9ff"}},
    {x,y:atl,type:"scatter",mode:"lines",name:"Fatigue (ATL)",line:{color:"#ff6b6b"}},
    {x,y:tsb,type:"scatter",mode:"lines",name:"Form (TSB)",line:{color:"#3ddc97",dash:"dot"}},
  ], {...DARK, yaxis:{...DARK.yaxis,title:"load units"}, xaxis:{...DARK.xaxis,title:"date"}}, {responsive:true});

  document.getElementById("load_meta").textContent =
    `HRmax observed ~${fmt(data.hrmax_observed,0)} bpm · missing-HR sessions in window=${data.hr_missing_sessions_in_window}`;
}

function recBadge(rec){
  const c = rec==="good" ? "#3ddc97" : (rec==="caution" ? "#ffcc66" : "#ff6b6b");
  const t = rec==="good" ? "✅ sensible" : (rec==="caution" ? "⚠️ caution" : "⛔ risky");
  return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid ${c};color:${c}">${t}</span>`;
}

async function renderScenarios(){
  const dur = Number(document.getElementById("dur").value);
  const intensity = Number(document.getElementById("intensity").value);

  document.getElementById("dur_lbl").textContent = dur;
  document.getElementById("int_lbl").textContent = Math.round(intensity*100) + "%";

  const data = await fetchJSON(`${API}/api/scenarios_dynamic?days=14&dur_min=${dur}&intensity=${intensity}`);
  if(data.status !== "ok") return;

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
  `;

  const N = s[0].series.tsb.length;
  const x = Array.from({length:N}, (_,i)=>`D+${i+1}`);
  const traces = s.map(o=>({
    x, y:o.series.tsb, type:"scatter", mode:"lines", name:o.name, line:{width:2}
  }));

  Plotly.newPlot("scenario_plot", traces, {
    ...DARK,
    yaxis:{...DARK.yaxis,title:"Form (TSB)"},
    xaxis:{...DARK.xaxis,title:"projection horizon"},
  }, {responsive:true});
}

function attachScenarioControls(){
  const dur = document.getElementById("dur");
  const intensity = document.getElementById("intensity");
  const rerender = () => renderScenarios().catch(console.error);
  dur.addEventListener("input", rerender);
  intensity.addEventListener("input", rerender);
}

(async function main(){
  try{
    await renderLongTermLoad();
    attachScenarioControls();
    await renderScenarios();
  }catch(e){
    console.error(e);
    alert("Dashboard couldn't load API data. If Render was sleeping, refresh.");
  }
})();
