(function () {
  function textOf(el) {
    return (el && el.textContent ? el.textContent : '').trim().toLowerCase();
  }

  function headingText(node) {
    if (!node) return '';
    if (node.id === 'cards' || node.id === 'scienceCards') return 'summary cards';
    const h = node.querySelector && node.querySelector('h2, h1');
    return textOf(h);
  }

  function classify(node) {
    const h = headingText(node);
    const id = node.id || '';
    const cls = node.className || '';

    if (id === 'cards' || id === 'scienceCards' || h.includes('suggested next') || h.includes('load caution') || h.includes('current advice') || h.includes('this week')) return 'Today';
    if (h.includes('ctl') || h.includes('threshold') || h.includes('easy-run') || h.includes('speed per heartbeat') || h.includes('steady-run') || h.includes('aerobic durability') || h.includes('daily load') || h.includes('pace trend') || h.includes('fitness') || cls.includes('grid')) return 'Fitness trends';
    if (h.includes('race outlook') || h.includes('race prediction') || h.includes('training priorities') || h.includes('weak points') || h.includes('readiness')) return 'Race estimates';
    if (h.includes('matched') || h.includes('route') || h.includes('gps')) return 'Routes';
    if (h.includes('run type') || h.includes('training block') || h.includes('weekly') || h.includes('heatmap') || h.includes('fun stats')) return 'Training balance';
    if (h.includes('data quality') || h.includes('recent activities') || h.includes('privacy') || h.includes('method') || h.includes('details')) return 'Details / QA';
    return 'Details / QA';
  }

  const order = [
    { name: 'Today', open: true },
    { name: 'Fitness trends', open: true },
    { name: 'Race estimates', open: true },
    { name: 'Routes', open: true },
    { name: 'Training balance', open: false },
    { name: 'Details / QA', open: false },
  ];

  function makeSummaryStrip() {
    const header = document.querySelector('header');
    if (!header || document.querySelector('.dashboard-summary-strip')) return;
    const strip = document.createElement('section');
    strip.className = 'dashboard-summary-strip';
    strip.innerHTML = `
      <div class="summary-pill"><div class="label">Updated</div><div class="value" id="rmSumUpdated">—</div></div>
      <div class="summary-pill"><div class="label">Last 7 days</div><div class="value" id="rmSum7d">—</div></div>
      <div class="summary-pill"><div class="label">TSB</div><div class="value" id="rmSumTsb">—</div></div>
      <div class="summary-pill"><div class="label">Caution</div><div class="value" id="rmSumCaution">—</div></div>
      <div class="summary-pill"><div class="label">Suggested</div><div class="value" id="rmSumSuggested">—</div></div>
    `;
    header.insertAdjacentElement('afterend', strip);

    Promise.all([
      fetch('./data/summary.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : {}).catch(() => ({})),
      fetch('./data/insights.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : {}).catch(() => ({})),
    ]).then(([summary, insights]) => {
      const updated = summary.generated_at_utc ? new Date(summary.generated_at_utc).toLocaleString('en-GB') : '—';
      const d7 = summary.last_7d_distance_km !== undefined ? `${summary.last_7d_distance_km} km` : '—';
      const tsb = summary.tsb !== undefined ? summary.tsb : '—';
      const caution = insights.load_caution && insights.load_caution.level ? insights.load_caution.level : '—';
      const suggested = insights.suggested_next_run && insights.suggested_next_run.title ? insights.suggested_next_run.title : '—';
      const set = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
      set('rmSumUpdated', updated);
      set('rmSum7d', d7);
      set('rmSumTsb', tsb);
      set('rmSumCaution', caution);
      set('rmSumSuggested', suggested);
    });
  }

  function reorganiseMain() {
    const main = document.querySelector('main');
    if (!main || main.dataset.layoutRefactored === '1') return;

    const children = Array.from(main.children).filter(el => {
      if (el.classList && el.classList.contains('dashboard-section')) return false;
      if (el.tagName && el.tagName.toLowerCase() === 'script') return false;
      return true;
    });

    if (!children.length) return;

    const buckets = new Map(order.map(o => [o.name, []]));
    for (const child of children) {
      const group = classify(child);
      buckets.get(group).push(child);
    }

    main.innerHTML = '';

    for (const o of order) {
      const items = buckets.get(o.name) || [];
      if (!items.length) continue;
      const details = document.createElement('details');
      details.className = 'dashboard-section';
      if (o.open) details.open = true;
      const summary = document.createElement('summary');
      summary.textContent = o.name;
      const body = document.createElement('div');
      body.className = 'dashboard-section-body';
      for (const item of items) body.appendChild(item);
      details.appendChild(summary);
      details.appendChild(body);
      main.appendChild(details);
    }

    main.dataset.layoutRefactored = '1';
  }

  function enhanceRouteCards() {
    // If matched_runs.json has route_image fields but an older renderer is active,
    // this adds thumbnails into matched-route verdict cards after rendering.
    fetch('./data/matched_runs.json', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || !data.items) return;
        const byLabel = new Map(data.items.map(x => [x.label, x.route_image]));
        document.querySelectorAll('.mini-card').forEach(card => {
          if (card.querySelector('.route-thumb')) return;
          const labelEl = card.querySelector('.mini-card-rank');
          const label = labelEl ? labelEl.textContent.trim() : '';
          const img = byLabel.get(label);
          if (!img) return;
          const image = document.createElement('img');
          image.className = 'route-thumb';
          image.src = img;
          image.alt = `Pictographic route sketch for ${label}`;
          card.classList.add('route-card');
          card.insertBefore(image, card.firstChild);
        });
      })
      .catch(() => {});
  }

  function run() {
    makeSummaryStrip();
    // Let existing app/insights scripts populate first; then group the rendered panels.
    window.setTimeout(() => {
      reorganiseMain();
      enhanceRouteCards();
      window.setTimeout(enhanceRouteCards, 500);
    }, 250);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
