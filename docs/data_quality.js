async function dqLoad(path, fallback) {
  try {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) return fallback;
    return await res.json();
  } catch {
    return fallback;
  }
}

function dqRender(q) {
  const el = document.getElementById('dataQualityPanel');
  if (!el) return;

  el.innerHTML = `
    <div class="mini-grid">
      <div class="mini-card">
        <div class="mini-card-rank">Public activities</div>
        <h3>${q.activities_recent_public ?? '—'}</h3>
      </div>
      <div class="mini-card">
        <div class="mini-card-rank">Local stream files</div>
        <h3>${q.local_stream_files ?? '—'}</h3>
      </div>
      <div class="mini-card">
        <div class="mini-card-rank">Threshold points</div>
        <h3>${q.threshold_points ?? '—'}</h3>
      </div>
      <div class="mini-card">
        <div class="mini-card-rank">GPS matched groups</div>
        <h3>${q.matched_route_groups ?? '—'}</h3>
      </div>
    </div>
    <p class="small">${q.note || ''}</p>
  `;
}

function dqRelabelMatchedRuns() {
  document.querySelectorAll('th').forEach(th => {
    const text = th.textContent.trim();
    if (text === 'Efficiency') th.textContent = 'Speed per heartbeat';
    if (text === 'Eff. vs previous') th.textContent = 'SPH vs previous';
  });
}

async function dqMain() {
  const q = await dqLoad('./data/data_quality.json', {});
  dqRender(q);
  dqRelabelMatchedRuns();
}

dqMain();
