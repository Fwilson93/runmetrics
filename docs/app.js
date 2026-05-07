(function(){
  const BASE = window.location.origin + window.location.pathname.replace(/\/$/, "");
  const DATA = BASE + "/data";

  function byId(id){ return document.getElementById(id); }
  function fmt(x, dp=1){
    if(x===null||x===undefined||Number.isNaN(Number(x))) return "–";
    return Number(x).toFixed(dp);
  }
  function fetchJSON(p){
    return fetch(p, {cache:"no-store"}).then(r=>{
      if(!r.ok) throw new Error(r.status+" "+r.statusText+" :: "+p);
      return r.json();
    });
  }
  function sliceLast(arr,n){ return (arr && arr.length>n) ? arr.slice(arr.length-n) : (arr||[]); }

  function plotLoad(series, generated_at){
    const el = byId("load_plot");
    const meta = byId("load_meta");
    const s = sliceLast(series, 120);
    const x = s.map(p=>p.date);
    const ctl = s.map(p=>p.ctl);
    const atl = s.map(p=>p.atl);
    const tsb = s.map(p=>p.tsb);

    Plotly.newPlot(el, [
      {x,y:ctl,type:"scatter",mode:"lines",name:"CTL",line:{color:"#6aa9ff",width:3}},
      {x,y:atl,type:"scatter",mode:"lines",name:"ATL",line:{color:"#ff6b6b",width:3}},
      {x,y:tsb,type:"scatter",mode:"lines",name:"TSB",line:{color:"#3ddc97",width:3}},
    ], {
      paper_bgcolor:"#0f1117",plot_bgcolor:"#0f1117",font:{color:"#e9eef6"},
      xaxis:{gridcolor:"#1f2430"},yaxis:{gridcolor:"#1f2430",title:"load"},
      margin:{t:20,l:55,r:10,b:45},legend:{orientation:"h"}
    }, {displayModeBar:false,responsive:true});

    if(meta && s.length){
      const last = s[s.length-1];
      meta.textContent = "Last update: " + (generated_at||"").slice(0,19).replace("T"," ") +
        " UTC · CTL " + fmt(last.ctl,1) + " · ATL " + fmt(last.atl,1) + " · TSB " + fmt(last.tsb,1);
    }
  }

  function renderInsights(j){
    const el = byId("insights");
    if(!el || !j || j.status!=="ok") return;
    const acwr = (j.acwr===null||j.acwr===undefined) ? "–" : Number(j.acwr).toFixed(2);
    const notes = (j.lower_leg_risk_notes||[]).map(x=>"<li>"+x+"</li>").join("");
    el.innerHTML =
      "<strong>Trend:</strong> "+j.trend+
      " · <strong>Freshness:</strong> "+j.freshness+
      " · <strong>ACWR:</strong> "+acwr+
      " · <strong>Lower‑leg risk:</strong> "+j.lower_leg_risk_level+
      "<br><span class='muted'>"+j.note+"</span>" +
      (notes?("<ul class='muted' style='margin:6px 0 0 18px'>"+notes+"</ul>"):"");
  }

  function plotWeekly(weeks){
    const el = byId("weekly_plot");
    if(!el || !weeks || !weeks.length) return;
    const x = weeks.map(w=>w.week_start);
    const y = weeks.map(w=>w.distance_km);
    Plotly.newPlot(el, [
      {x,y,type:"bar",name:"Distance (km)",marker:{color:"#3ddc97"}}
    ], {
      paper_bgcolor:"#0f1117",plot_bgcolor:"#0f1117",font:{color:"#e9eef6"},
      xaxis:{gridcolor:"#1f2430",title:"week start"},yaxis:{gridcolor:"#1f2430",title:"km"},
      margin:{t:20,l:55,r:10,b:60},showlegend:false
    }, {displayModeBar:false,responsive:true});
  }

  function renderRecent(items){
    const el = byId("recent_list");
    if(!el) return;
    if(!items || !items.length){ el.textContent="No recent activities."; return; }
    el.innerHTML = items.slice(0,25).map(a=>{
      const d = (a.date||"").slice(0,10);
      const hr = (a.avg_hr===null||a.avg_hr===undefined) ? "–" : Math.round(a.avg_hr)+" bpm";
      const dist = (a.distance_km===null||a.distance_km===undefined) ? "–" : fmt(a.distance_km,1)+" km";
      const pace = (a.pace_min_per_km===null||a.pace_min_per_km===undefined) ? "–" : fmt(a.pace_min_per_km,2)+" min/km";
      return "<div style='margin-bottom:6px'><strong>"+d+"</strong> — "+(a.name||"Activity")+
        " <span class='muted'>("+dist+", "+pace+", HR "+hr+")</span></div>";
    }).join("");
  }

  function boot(){
    fetchJSON(DATA + "/load_365.json").then(j=>{
      if(j && j.series) plotLoad(j.series, j.generated_at);
    }).catch(console.error);

    fetchJSON(DATA + "/insights.json").then(j=>{
      renderInsights(j);
    }).catch(console.error);

    fetchJSON(DATA + "/weekly.json").then(j=>{
      if(j && j.weeks) plotWeekly(j.weeks);
    }).catch(console.error);

    fetchJSON(DATA + "/recent.json").then(j=>{
      renderRecent(j.items||[]);
    }).catch(console.error);
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();