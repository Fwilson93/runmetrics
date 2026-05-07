/* RunMetrics – static GitHub Pages renderer (no Render API)
 *
 * Reads:
 *   docs/data/load_365.json
 *   docs/data/recent.json
 *
 * Renders into:
 *   #load_plot, #load_meta, #recent_list
 */

(function () {
  "use strict";

  var BASE = window.location.origin + window.location.pathname.replace(/\/$/, "");
  var DATA = BASE + "/data";

  function byId(id) {
    return document.getElementById(id);
  }

  function fmt(x, dp) {
    if (x === null || x === undefined || Number.isNaN(Number(x))) return "–";
    return Number(x).toFixed(dp === undefined ? 1 : dp);
  }

  function sliceLast(arr, n) {
    if (!arr) return [];
    if (arr.length <= n) return arr;
    return arr.slice(arr.length - n);
  }

  function fetchJSON(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error(r.status + " " + r.statusText + " :: " + url);
      return r.json();
    });
  }

  function plotLoad(series, generatedAt) {
    var plotDiv = byId("load_plot");
    var metaDiv = byId("load_meta");
    if (!plotDiv) return;

    if (typeof Plotly === "undefined") {
      if (metaDiv) metaDiv.textContent = "Plotly failed to load.";
      return;
    }

    var s = sliceLast(series, 120);
    var x = s.map(function (p) { return p.date; });
    var ctl = s.map(function (p) { return p.ctl; });
    var atl = s.map(function (p) { return p.atl; });
    var tsb = s.map(function (p) { return p.tsb; });

    var layout = {
      paper_bgcolor: "#0f1117",
      plot_bgcolor: "#0f1117",
      font: { color: "#e9eef6" },
      xaxis: { gridcolor: "#1f2430", zerolinecolor: "#1f2430", title: "date" },
      yaxis: { gridcolor: "#1f2430", zerolinecolor: "#1f2430", title: "load" },
      margin: { t: 20, l: 55, r: 10, b: 45 },
      legend: { orientation: "h" }
    };

    var traces = [
      { x: x, y: ctl, type: "scatter", mode: "lines", name: "CTL (fitness)", line: { color: "#6aa9ff", width: 3 } },
      { x: x, y: atl, type: "scatter", mode: "lines", name: "ATL (fatigue)", line: { color: "#ff6b6b", width: 3 } },
      { x: x, y: tsb, type: "scatter", mode: "lines", name: "TSB (form)", line: { color: "#3ddc97", width: 3 } }
    ];

    Plotly.newPlot(plotDiv, traces, layout, { displayModeBar: false, responsive: true });

    if (metaDiv && s.length) {
      var last = s[s.length - 1];
      var stamp = (generatedAt || "").slice(0, 19).replace("T", " ");
      metaDiv.textContent =
        "Last update: " + stamp + " UTC · CTL " + fmt(last.ctl, 1) +
        " · ATL " + fmt(last.atl, 1) + " · TSB " + fmt(last.tsb, 1);
    }
  }

  function renderRecent(items) {
    var host = byId("recent_list");
    if (!host) return;

    if (!items || !items.length) {
      host.textContent = "No recent activities found.";
      return;
    }

    // Keep it simple + robust (no template strings)
    var html = "";
    for (var i = 0; i < items.length; i++) {
      var a = items[i] || {};
      var d = (a.date || "").slice(0, 10);
      var name = a.name || a.sport_type || "Activity";
      var dist = (a.distance_km !== null && a.distance_km !== undefined) ? fmt(a.distance_km, 1) + " km" : "–";
      var pace = (a.pace_min_per_km !== null && a.pace_min_per_km !== undefined) ? fmt(a.pace_min_per_km, 2) + " min/km" : "–";
      var hr = (a.avg_hr !== null && a.avg_hr !== undefined) ? String(Math.round(a.avg_hr)) + " bpm" : "–";

      html += "<div style=\"margin-bottom:6px\">";
      html += "<strong>" + d + "</strong> — " + name;
      html += " <span class=\"muted\">(" + dist + ", " + pace + ", HR " + hr + ")</span>";
      html += "</div>";
    }
    host.innerHTML = html;
  }
/* RM_STATIC_INSIGHTS_V2 */
    /* RM_STATIC_INSIGHTS_FIXED */
  function renderInsights(series){
    var el = document.getElementById("insights_panel");
    if(!el || !series || series.length < 30) return;

    var last = series[series.length - 1];

    function avg(arr){
      var s = 0;
      for(var i=0;i<arr.length;i++) s += arr[i];
      return arr.length ? (s/arr.length) : 0;
    }

    var last7  = series.slice(-7);
    var last28 = series.slice(-28);

    var load7  = avg(last7.map(function(d){ return d.daily_load || 0; }));
    var load28 = avg(last28.map(function(d){ return d.daily_load || 0; }));

    var trend = "stable";
    if(load7 > load28 * 1.10) trend = "rising";
    else if(load7 < load28 * 0.90) trend = "falling";

    var freshness = "balanced";
    if(last.tsb > 5) freshness = "fresh";
    else if(last.tsb < -10) freshness = "fatigued";

    var trainingDays7 = last7.filter(function(d){ return (d.daily_load || 0) > 0; }).length;

    el.innerHTML =
      "<strong>Current state</strong><br>" +
      "Load trend: " + trend + " (7d vs 28d)<br>" +
      "Freshness: " + freshness + " (TSB " + fmt(last.tsb,1) + ")<br>" +
      "Training days (last 7): " + trainingDays7 + " / 7<br>" +
      "<span class=\"muted\">Use directionally (decision support), not as a precise forecast.</span>";
  }
    var last7  = series.slice(-7);
    var last28 = series.slice(-28);

    var load7  = avg(last7.map(function(d){ return d.daily_load || 0; }));
    var load28 = avg(last28.map(function(d){ return d.daily_load || 0; }));

    var trend = "stable";
    if(load7 > load28 * 1.10) trend = "rising";
    else if(load7 < load28 * 0.90) trend = "falling";

    var freshness = "balanced";
    if(last.tsb > 5) freshness = "fresh";
    else if(last.tsb < -10) freshness = "fatigued";

    var trainingDays7 = last7.filter(function(d){ return (d.daily_load || 0) > 0; }).length;

    el.innerHTML =
      "<strong>Current state</strong><br>" +
      "Load trend: " + trend + " (7d vs 28d)<br>" +
      "Freshness: " + freshness + " (TSB " + fmt(last.tsb,1) + ")<br>" +
      "Training days (last 7): " + trainingDays7 + " / 7<br>" +
      "<span class=\"muted\">Use directionally (decision support), not as a precise forecast.</span>";
  }

    var last7  = series.slice(-7);
    var last28 = series.slice(-28);

    var load7  = avg(last7.map(function(d){ return d.daily_load || 0; }));
    var load28 = avg(last28.map(function(d){ return d.daily_load || 0; }));

    var trend = "stable";
    if(load7 > load28 * 1.10) trend = "rising";
    else if(load7 < load28 * 0.90) trend = "falling";

    var freshness = "balanced";
    if(last.tsb > 5) freshness = "fresh";
    else if(last.tsb < -10) freshness = "fatigued";

    var trainingDays7 = last7.filter(function(d){ return (d.daily_load || 0) > 0; }).length;

    el.innerHTML =
      "<strong>Current state</strong><br>" +
      "Load trend: " + trend + " (7d vs 28d)<br>" +
      "Freshness: " + freshness + " (TSB " + (Math.round(last.tsb*10)/10) + ")<br>" +
      "Training days (last 7): " + trainingDays7 + " / 7<br>" +
  }



  function boot() {
    // Load plot
    fetchJSON(DATA + "/load_365.json")
      .then(function (j) {
        if (j && j.series && j.series.length) {
          plotLoad(j.series, j.generated_at);
          renderInsights(j.series);
        } else {
          var metaDiv = byId("load_meta");
          if (metaDiv) metaDiv.textContent = "No load series found in load_365.json.";
        }
      })
      .catch(function (e) {
        console.error(e);
        var metaDiv = byId("load_meta");
        if (metaDiv) metaDiv.textContent = "Failed to load load_365.json (see console).";
      });

    // Load recent list (support both {items:[]} and {activities:[]} just in case)
    fetchJSON(DATA + "/recent.json")
      .then(function (j) {
        var items = (j && j.items) ? j.items : ((j && j.activities) ? j.activities : []);
        renderRecent(items);
      })
      .catch(function (e) {
        console.error(e);
        var host = byId("recent_list");
        if (host) host.textContent = "Failed to load recent.json (see console).";
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

