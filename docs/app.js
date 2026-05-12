const fmt = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 });
const fmt2 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });

async function loadJson(path) {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return await res.json();
}

async function loadJsonOptional(path, fallback) {
  try {
    return await loadJson(path);
  } catch (err) {
    console.warn(`Optional data not available: ${path}`, err);
    return fallback;
  }
}

function pace(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const mins = Math.floor(Number(v));
  const secs = Math.round((Number(v) - mins) * 60);
  return `${mins}:${String(secs).padStart(2, '0')}/km`;
}

function card(label, value, unit = '') {
  return `<div class="card"><div class="label">${label}</div><div class="value">${value ?? '—'}</div><div class="unit">${unit}</div></div>`;
}

function makeLineChart(id, labels, datasets, yTitle = '') {
  const ctx = document.getElementById(id);
  return new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#e8eefc' } } },
      scales: {
        x: { ticks: { color: '#99a7c7', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,0.06)' } },
        y: { title: { display: Boolean(yTitle), text: yTitle, color: '#99a7c7' }, ticks: { color: '#99a7c7' }, grid: { color: 'rgba(255,255,255,0.06)' } }
      }
    }
  });
}

function makeBarChart(id, labels, datasets, yTitle = '') {
  const ctx = document.getElementById(id);
  return new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e8eefc' } } },
      scales: {
        x: { ticks: { color: '#99a7c7', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,0.06)' } },
        y: { title: { display: Boolean(yTitle), text: yTitle, color: '#99a7c7' }, ticks: { color: '#99a7c7' }, grid: { color: 'rgba(255,255,255,0.06)' } }
      }
    }
  });
}


function makeThresholdChart(thresholdHistory) {
  const canvas = document.getElementById('thresholdZones');
  const note = document.getElementById('thresholdNote');

  if (!canvas || !note) return;

  const items = thresholdHistory && thresholdHistory.items ? thresholdHistory.items : [];

  if (!items.length) {
    note.textContent = 'No threshold-history data yet. Run the stream fetcher and stream analysis first.';
    return;
  }

  note.textContent = `${thresholdHistory.method} ${thresholdHistory.zone_model || ''}`;

  makeLineChart('thresholdZones', items.map(d => d.date), [
    {
      label: 'Estimated threshold HR proxy',
      data: items.map(d => d.threshold_hr_proxy),
      borderColor: '#f472b6',
      backgroundColor: 'transparent',
      tension: 0.25,
      borderWidth: 3
    },
    {
      label: 'Z2 lower',
      data: items.map(d => d.z2_lower),
      borderColor: 'rgba(126,231,135,0.7)',
      backgroundColor: 'transparent',
      tension: 0.25,
      borderDash: [6, 4]
    },
    {
      label: 'Z2 upper',
      data: items.map(d => d.z2_upper),
      borderColor: 'rgba(126,231,135,0.95)',
      backgroundColor: 'transparent',
      tension: 0.25
    },
    {
      label: 'Z3 upper',
      data: items.map(d => d.z3_upper),
      borderColor: 'rgba(255,209,102,0.95)',
      backgroundColor: 'transparent',
      tension: 0.25
    },
    {
      label: 'Z4 upper',
      data: items.map(d => d.z4_upper),
      borderColor: 'rgba(255,123,114,0.95)',
      backgroundColor: 'transparent',
      tension: 0.25
    }
  ], 'bpm');
}


function renderScienceCards(summary, thresholdHistory, driftSummary, matchedRuns) {
  const el = document.getElementById('scienceCards');
  if (!el) return;

  const latest = thresholdHistory.latest || (
    thresholdHistory.items && thresholdHistory.items.length
      ? thresholdHistory.items[thresholdHistory.items.length - 1]
      : null
  );

  const driftItems = driftSummary.items || [];
  const lastDrift = driftItems.length ? driftItems[driftItems.length - 1] : null;
  const matchedCount = matchedRuns.items ? matchedRuns.items.length : 0;

  el.innerHTML = [
    card('Threshold proxy', latest ? fmt.format(latest.threshold_hr_proxy) : '—', latest ? `bpm; ${latest.confidence} confidence` : 'no stream estimate yet'),
    card('Eligible windows', latest ? latest.eligible_windows : '—', 'rolling lookback'),
    card('Latest drift', lastDrift ? fmt.format(lastDrift.efficiency_change_pct) : '—', '% efficiency change'),
    card('Matched groups', matchedCount, 'approximate distance/elevation matches')
  ].join('');
}

function makeDriftChart(driftSummary) {
  const canvas = document.getElementById('driftChart');
  const note = document.getElementById('driftNote');

  if (!canvas || !note) return;

  const items = driftSummary.items || [];

  if (!items.length) {
    note.textContent = 'No drift summary yet. More stream files or longer steady runs are needed.';
    return;
  }

  note.textContent = driftSummary.method || '';

  makeLineChart('driftChart', items.map(d => d.date), [
    {
      label: 'Efficiency change %',
      data: items.map(d => d.efficiency_change_pct),
      borderColor: '#67e8f9',
      backgroundColor: 'transparent',
      tension: 0.25,
      borderWidth: 3
    },
    {
      label: 'HR rise bpm',
      data: items.map(d => d.hr_rise_bpm),
      borderColor: '#ffd166',
      backgroundColor: 'transparent',
      tension: 0.25
    }
  ], '% / bpm');
}

function renderMatchedRuns(matchedRuns) {
  const table = document.querySelector('#matchedRunsTable tbody');
  const note = document.getElementById('matchedRunsNote');

  if (!table || !note) return;

  const items = matchedRuns.items || [];
  note.textContent = matchedRuns.method || '';

  if (!items.length) {
    table.innerHTML = '<tr><td colspan="9">No matched-run groups yet.</td></tr>';
    return;
  }

  table.innerHTML = items.map(r => `
    <tr>
      <td>${r.label}</td>
      <td>${r.count}</td>
      <td>${r.latest_date}</td>
      <td>${fmt.format(r.typical_distance_km)}</td>
      <td>${fmt.format(r.typical_elev_gain_m)}</td>
      <td>${pace(r.latest_pace_min_per_km)}</td>
      <td>${r.latest_avg_hr === null ? '—' : fmt.format(r.latest_avg_hr)}</td>
      <td>${r.latest_efficiency_kmh_per_bpm === null || r.latest_efficiency_kmh_per_bpm === undefined ? '—' : fmt2.format(r.latest_efficiency_kmh_per_bpm)}</td>
      <td>${r.latest_vs_previous_median_efficiency_pct === null || r.latest_vs_previous_median_efficiency_pct === undefined ? '—' : fmt.format(r.latest_vs_previous_median_efficiency_pct) + '%'}</td>
      <td>${r.fitness_signal || '—'}</td>
    </tr>`).join('');
}

async function main() {
  const [summary, daily, weekly, recent, thresholdHistory, driftSummary, matchedRuns] = await Promise.all([
    loadJson('./data/summary.json'),
    loadJson('./data/daily_metrics.json'),
    loadJson('./data/weekly_metrics.json'),
    loadJson('./data/activities_recent.json'),
    loadJsonOptional('./data/threshold_history.json', { items: [], method: '', latest: null }),
    loadJsonOptional('./data/drift_summary.json', { items: [], method: '' }),
    loadJsonOptional('./data/matched_runs.json', { items: [], method: '' })
  ]);

  document.getElementById('generated').textContent = `Updated ${new Date(summary.generated_at_utc).toLocaleString('en-GB')}`;
  document.getElementById('cards').innerHTML = [
    card('Last 7 days', fmt.format(summary.last_7d_distance_km), 'km'),
    card('Last 28 days', fmt.format(summary.last_28d_distance_km), 'km'),
    card('CTL', fmt.format(summary.ctl), 'fitness'),
    card('ATL', fmt.format(summary.atl), 'fatigue'),
    card('TSB', fmt.format(summary.tsb), 'form'),
    card('ACWR', fmt2.format(summary.acwr), '7d / 28d load'),
    card('Observed HRmax', fmt.format(summary.observed_hrmax), 'bpm'),
    card('Activities', summary.activity_count, `${summary.date_min} → ${summary.date_max}`),
  ].join('');

  const advice = document.getElementById('advice');
  advice.innerHTML = summary.advice.map(x => `<li>${x}</li>`).join('');

  makeBarChart('weeklyDistance', weekly.map(d => d.date), [
    { label: 'Weekly km', data: weekly.map(d => d.distance_km), backgroundColor: 'rgba(103,232,249,0.55)' },
    { label: '4-week average', data: weekly.map(d => d.distance_4w_avg), type: 'line', borderColor: '#7ee787', backgroundColor: 'transparent', tension: 0.25 }
  ], 'km');

  makeLineChart('pmc', daily.map(d => d.date), [
    { label: 'CTL / fitness', data: daily.map(d => d.ctl), borderColor: '#67e8f9', backgroundColor: 'transparent', tension: 0.2 },
    { label: 'ATL / fatigue', data: daily.map(d => d.atl), borderColor: '#ff7b72', backgroundColor: 'transparent', tension: 0.2 },
    { label: 'TSB / form', data: daily.map(d => d.tsb), borderColor: '#7ee787', backgroundColor: 'transparent', tension: 0.2 },
  ], 'load units');

  makeBarChart('dailyLoad', daily.map(d => d.date), [
    { label: 'Daily load', data: daily.map(d => d.load_trimp), backgroundColor: 'rgba(255,209,102,0.45)' },
    { label: '7-day load', data: daily.map(d => d.load_7d), type: 'line', borderColor: '#67e8f9', backgroundColor: 'transparent', tension: 0.2 }
  ], 'TRIMP-derived load');

  makeLineChart('paceTrend', daily.map(d => d.date), [
    { label: 'Mean pace, active days', data: daily.map(d => d.pace_min_per_km), borderColor: '#c084fc', backgroundColor: 'transparent', tension: 0.2 }
  ], 'min/km');

  renderScienceCards(summary, thresholdHistory, driftSummary, matchedRuns);
  makeThresholdChart(thresholdHistory);
  makeDriftChart(driftSummary);
  renderMatchedRuns(matchedRuns);

  const tbody = document.querySelector('#recentTable tbody');
  tbody.innerHTML = recent.map(r => `
    <tr>
      <td>${r.date}</td>
      <td>${r.sport_type}</td>
      <td>${fmt.format(r.distance_km)}</td>
      <td>${fmt.format(r.moving_time_min)}</td>
      <td>${pace(r.pace_min_per_km)}</td>
      <td>${fmt.format(r.elev_gain_m)}</td>
      <td>${r.avg_hr === null ? '—' : fmt.format(r.avg_hr)}</td>
      <td>${fmt.format(r.load_trimp)}</td>
    </tr>`).join('');
}

main().catch(err => {
  document.body.innerHTML = `<main class="panel"><h1>RunMetrics failed to load</h1><pre>${err.stack || err}</pre></main>`;
});

// Route thumbnails for matched-run table/cards, if present in matched_runs.json.
(function addRouteThumbStylesHook(){
  window.runmetricsRouteThumbsEnabled = true;
})();
