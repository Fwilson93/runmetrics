async function rmLoadJsonOptional(path, fallback) {
  try {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) return fallback;
    return await res.json();
  } catch {
    return fallback;
  }
}

function rmFmt(x, digits = 1) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits }).format(Number(x));
}

function rmPace(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const mins = Math.floor(Number(v));
  const secs = Math.round((Number(v) - mins) * 60);
  return `${mins}:${String(secs).padStart(2, '0')}/km`;
}

function rmRenderList(id, items) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = (items || []).map(x => `<li>${x}</li>`).join('');
}

function rmRenderSuggestedNextRun(insights) {
  const el = document.getElementById('suggestedNextRun');
  if (!el) return;
  const data = insights.suggested_next_run || {};
  const options = data.options || [];
  if (!options.length) {
    el.innerHTML = '<p class="small">No suggestion available yet.</p>';
    return;
  }
  el.innerHTML = options.map(o => `
    <div class="mini-card">
      <div class="mini-card-rank">Option ${o.rank}</div>
      <h3>${o.title}</h3>
      <p><strong>${o.session}</strong></p>
      <p>${o.why}</p>
      <p class="small">${o.intensity}</p>
    </div>
  `).join('');
}

function rmRenderLoadCaution(insights) {
  const el = document.getElementById('loadCaution');
  if (!el) return;
  const c = insights.load_caution || {};
  el.innerHTML = `
    <div class="caution caution-${c.level || 'unknown'}">
      <h3>${(c.level || 'unknown').toUpperCase()} caution</h3>
      <p>${c.message || ''}</p>
      <ul>${(c.reasons || []).map(r => `<li>${r}</li>`).join('')}</ul>
    </div>
  `;
}

function rmRenderDurability(insights) {
  const el = document.getElementById('durabilityPanel');
  if (!el) return;
  const d = insights.aerobic_durability || {};
  el.innerHTML = `
    <h3>${d.label || 'not enough data'} ${d.score ? `(${d.score}/100)` : ''}</h3>
    <p>${d.message || ''}</p>
    <p class="small">${d.plain_english || ''}</p>
  `;
}

function rmRenderTrainingBlocks(insights) {
  const tbody = document.querySelector('#trainingBlocksTable tbody');
  if (!tbody) return;
  const rows = insights.training_blocks || [];
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${r.label}</td>
      <td>${rmFmt(r.distance_km)}</td>
      <td>${rmFmt(r.mean_km_per_week)}</td>
      <td>${rmFmt(r.load, 0)}</td>
      <td>${rmFmt(r.elev_gain_m, 0)}</td>
      <td>${r.active_days}</td>
    </tr>
  `).join('');
}

function rmRenderFunStats(insights) {
  const el = document.getElementById('funStats');
  if (!el) return;
  const stats = insights.fun_stats || [];
  el.innerHTML = stats.map(s => `
    <div class="mini-card">
      <div class="mini-card-rank">${s.label}</div>
      <h3>${s.value}</h3>
      <p class="small">${s.context || ''}</p>
    </div>
  `).join('');
}

function rmRenderHeatmap(insights) {
  const el = document.getElementById('trainingHeatmap');
  if (!el) return;
  const cells = insights.heatmap || [];
  el.innerHTML = cells.map(c => `
    <span class="heat-cell heat-${c.bucket}" title="${c.date}: ${rmFmt(c.distance_km)} km"></span>
  `).join('');
}

function rmImproveDriftWording() {
  const heading = [...document.querySelectorAll('h2')].find(h => h.textContent.includes('HR drift'));
  if (heading) heading.textContent = 'Steady-run fade';

  const note = document.getElementById('driftNote');
  if (note) {
    note.textContent =
      'Plain English: this checks whether you get less speed for the same heartbeat in the second half of steady runs. ' +
      'Closer to 0% is better. A strongly negative efficiency change means you faded: HR rose, pace dropped, or both. ' +
      'Heat, hills, fatigue, fuelling and optical HR noise can all affect it.';
  }
}

async function rmInsightsMain() {
  const insights = await rmLoadJsonOptional('./data/insights.json', null);
  if (!insights) {
    rmImproveDriftWording();
    return;
  }

  rmRenderSuggestedNextRun(insights);
  rmRenderLoadCaution(insights);
  rmRenderList('weeklyDigest', insights.weekly_digest || []);
  rmRenderDurability(insights);
  rmRenderTrainingBlocks(insights);
  rmRenderFunStats(insights);
  rmRenderHeatmap(insights);
  rmImproveDriftWording();

  const privacy = document.getElementById('privacyNote');
  if (privacy && insights.privacy) {
    privacy.textContent = insights.privacy.public_site_policy;
  }
}

rmInsightsMain();
