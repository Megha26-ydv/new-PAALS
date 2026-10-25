/* suppliers.js — supplier registry with tier/region/deviation filters */

let allSuppliers = [];

function fmt(v) {
  if (!v && v !== 0) return '—';
  if (v >= 1000000) return `$${(v / 1000000).toFixed(1)}M`;
  if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`;
  return `$${Number(v).toFixed(0)}`;
}

function tierBadge(tier) {
  const map = {
    1: ['critical', 'T1 · Strategic'],
    2: ['high',     'T2 · Preferred'],
    3: ['medium',   'T3 · Standard'],
  };
  const [cls, label] = map[tier] || ['blue', `T${tier}`];
  return `<span class="badge ${cls}">${label}</span>`;
}

function reliabilityBar(score) {
  const pct = Math.round(score * 100);
  const color = pct >= 90 ? 'var(--low)' : pct >= 80 ? '#9cc77f' : pct >= 70 ? 'var(--medium)' : 'var(--critical)';
  return `
    <div style="display:flex;align-items:center;gap:6px;">
      <div style="width:56px;height:4px;background:var(--bg-raised);border-radius:2px;overflow:hidden;">
        <div style="width:${pct}%;height:100%;background:${color};border-radius:2px;"></div>
      </div>
      <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);">${pct}%</span>
    </div>`;
}

function renderTable(rows) {
  const tbody = document.getElementById('supplier-tbody');
  document.getElementById('row-count').textContent = `${rows.length} supplier${rows.length !== 1 ? 's' : ''}`;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="12" style="padding:28px;text-align:center;
        color:var(--text-muted);">No suppliers match current filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(s => {
    const cats = Array.isArray(s.categories)
      ? s.categories.slice(0, 2).join(', ')
      : (s.categories || '—');

    const devCell = s.active_deviations > 0
      ? `<span class="badge ${s.active_deviations >= 3 ? 'critical' : 'high'}">${s.active_deviations}</span>`
      : `<span style="color:var(--text-muted);">—</span>`;

    const expCell = s.total_exposure > 0
      ? `<span style="font-family:var(--font-mono);color:var(--critical);">${fmt(s.total_exposure)}</span>`
      : `<span style="color:var(--text-muted);">—</span>`;

    return `<tr>
      <td class="mono">${s.id}</td>
      <td title="${s.name}" style="max-width:200px;">
        <span style="font-size:12px;color:var(--text-primary);">${s.name}</span>
      </td>
      <td class="text-secondary">${s.country}</td>
      <td class="text-secondary">${s.region}</td>
      <td>${tierBadge(s.strategic_tier)}</td>
      <td class="mono">${s.lead_time_days}d</td>
      <td>${reliabilityBar(s.reliability_score)}</td>
      <td class="mono">${fmt(s.annual_spend_usd)}</td>
      <td style="text-align:center;">${devCell}</td>
      <td>${expCell}</td>
      <td style="font-size:11px;color:var(--text-muted);max-width:150px;"
          class="truncate" title="${cats}">${cats}</td>
      <td class="mono">${s.currency}</td>
    </tr>`;
  }).join('');
}

function applyFilter() {
  const tier   = document.getElementById('tier-filter').value;
  const region = document.getElementById('region-filter').value;
  const devF   = document.getElementById('dev-filter').value;
  const source = document.getElementById('source-filter').value;
  let rows = allSuppliers;
  const prefix = { dataco: 'DC-', scms: 'SC-' }[source];
  if (prefix)      rows = rows.filter(s => s.id.startsWith(prefix));
  if (source === 'synthetic') rows = rows.filter(s => !s.id.startsWith('DC-') && !s.id.startsWith('SC-'));
  if (tier)        rows = rows.filter(s => String(s.strategic_tier) === tier);
  if (region)      rows = rows.filter(s => s.region === region);
  if (devF === '1') rows = rows.filter(s => s.active_deviations > 0);
  if (devF === '0') rows = rows.filter(s => s.active_deviations === 0);
  renderTable(rows);
}

function renderSpendByRegion(suppliers) {
  const map = {};
  suppliers.forEach(s => { map[s.region] = (map[s.region] || 0) + s.annual_spend_usd; });
  const sorted = Object.entries(map).sort((a, b) => b[1] - a[1]);
  const max = sorted[0][1];
  document.getElementById('spend-by-region').innerHTML = sorted.map(([region, spend]) => `
    <div style="padding:7px 0;border-bottom:1px solid var(--border);">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <span style="font-size:12px;color:var(--text-secondary);">${region}</span>
        <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);">${fmt(spend)}</span>
      </div>
      <div style="background:var(--bg-raised);border-radius:2px;height:3px;overflow:hidden;">
        <div style="background:var(--accent-blue);width:${(spend/max*100).toFixed(0)}%;
                    height:100%;border-radius:2px;"></div>
      </div>
    </div>`).join('');
}

function renderReliabilityDist(suppliers) {
  const buckets = { '90–100%': 0, '80–89%': 0, '70–79%': 0, '<70%': 0 };
  const colors  = { '90–100%': 'var(--low)', '80–89%': '#9cc77f', '70–79%': 'var(--medium)', '<70%': 'var(--critical)' };
  suppliers.forEach(s => {
    const pct = s.reliability_score * 100;
    if (pct >= 90)      buckets['90–100%']++;
    else if (pct >= 80) buckets['80–89%']++;
    else if (pct >= 70) buckets['70–79%']++;
    else                buckets['<70%']++;
  });
  const total = suppliers.length;
  document.getElementById('reliability-dist').innerHTML = Object.entries(buckets).map(([label, cnt]) => `
    <div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border);">
      <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);min-width:72px;">${label}</span>
      <div style="flex:1;background:var(--bg-raised);border-radius:2px;height:4px;overflow:hidden;">
        <div style="background:${colors[label]};width:${total > 0 ? (cnt/total*100).toFixed(0) : 0}%;
                    height:100%;border-radius:2px;"></div>
      </div>
      <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);
                   min-width:18px;text-align:right;">${cnt}</span>
    </div>`).join('');
}

async function loadSuppliers() {
  try {
    const suppliers = await fetch('/api/suppliers').then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
    allSuppliers = suppliers;

    document.getElementById('m-tier1').textContent = suppliers.filter(s => s.strategic_tier === 1).length;
    document.getElementById('m-tier2').textContent = suppliers.filter(s => s.strategic_tier === 2).length;
    document.getElementById('m-tier3').textContent = suppliers.filter(s => s.strategic_tier === 3).length;
    document.getElementById('m-with-dev').textContent = suppliers.filter(s => s.active_deviations > 0).length;

    // Populate region filter dynamically
    const regions = [...new Set(suppliers.map(s => s.region))].sort();
    const sel = document.getElementById('region-filter');
    regions.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r; opt.textContent = r;
      sel.appendChild(opt);
    });

    renderTable(suppliers);
    renderSpendByRegion(suppliers);
    renderReliabilityDist(suppliers);
  } catch (err) {
    document.getElementById('supplier-tbody').innerHTML =
      `<tr><td colspan="12" style="padding:28px;text-align:center;color:var(--critical);">
        Failed to load suppliers: ${err.message}</td></tr>`;
  }
}

loadSuppliers();
