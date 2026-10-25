/* deviations.js — deviation list with filter, sort, and tab switching */

let allRows = [];
let currentResolved = 0;

function devTypeLabel(t) {
  return t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function fmt(v) {
  if (!v && v !== 0) return '—';
  if (v >= 1000000) return `$${(v / 1000000).toFixed(2)}M`;
  if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`;
  return `$${Number(v).toFixed(0)}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' });
}

function renderTable(rows) {
  const tbody = document.getElementById('dev-tbody');
  const counter = document.getElementById('row-count');
  counter.textContent = `${rows.length} record${rows.length !== 1 ? 's' : ''}`;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="12" style="padding:28px;text-align:center;color:var(--text-muted);">
      No deviations match current filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(d => `
    <tr>
      <td class="mono">${d.id}</td>
      <td class="mono">${d.po_id}</td>
      <td>${devTypeLabel(d.deviation_type)}</td>
      <td style="max-width:160px;" class="truncate" title="${d.supplier_name}">${d.supplier_name}</td>
      <td class="text-secondary">${d.supplier_country || '—'}</td>
      <td><span class="badge ${d.severity}">${d.severity}</span></td>
      <td class="mono">${fmt(d.financial_exposure_usd)}</td>
      <td class="mono">${d.delay_days ?? '—'}</td>
      <td class="mono">${d.affected_customers.length}</td>
      <td class="mono" style="font-size:10px;white-space:nowrap;">${fmtDate(d.detected_at)}</td>
      <td>${d.agent_activated
        ? '<span class="badge approved">✓</span>'
        : '<span class="badge pending">—</span>'}</td>
      <td><a href="/deviations/${d.id}" class="btn btn-ghost btn-sm">Detail →</a></td>
    </tr>`).join('');
}

function applyFilters() {
  const typeF = document.getElementById('type-filter').value;
  const sevF = document.getElementById('sev-filter').value;
  let rows = allRows;
  if (typeF) rows = rows.filter(r => r.deviation_type === typeF);
  if (sevF) rows = rows.filter(r => r.severity === sevF);
  renderTable(rows);
}

async function loadDeviations(resolved) {
  currentResolved = resolved;
  const tbody = document.getElementById('dev-tbody');
  tbody.innerHTML = `<tr><td colspan="12" style="padding:28px;text-align:center;color:var(--text-muted);">
    Loading…</td></tr>`;

  try {
    const source = document.getElementById('source-filter').value;
    const rows = await fetch(`/api/deviations?resolved=${resolved}&limit=200&source=${source}`).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
    allRows = rows;
    document.getElementById('table-title').textContent =
      resolved ? 'Resolved Deviations' : 'Active Deviations';
    applyFilters();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="12" style="padding:28px;text-align:center;color:var(--critical);">
      Failed to load deviations: ${err.message}</td></tr>`;
  }
}

function setFilter(val, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  loadDeviations(val);
}

loadDeviations(0);
