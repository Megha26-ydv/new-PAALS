/* purchase_orders.js — PO list with status tabs, search, and deviation flags */

let allPOs = [];
let activeStatus = '';
let deviationPOs = new Set(); // PO IDs that have active deviations

function fmt(v) {
  if (!v && v !== 0) return '—';
  if (v >= 1000000) return `$${(v / 1000000).toFixed(2)}M`;
  if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`;
  return `$${Number(v).toFixed(0)}`;
}

function fmtDate(iso) {
  if (!iso) return '<span style="color:var(--text-muted);">—</span>';
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' });
}

function statusBadge(s) {
  const map = {
    in_transit:  ['blue',    'In Transit'],
    confirmed:   ['medium',  'Confirmed'],
    processing:  ['high',    'Processing'],
    delivered:   ['approved','Delivered'],
    on_hold:     ['high',    'On Hold'],
    cancelled:   ['rejected','Cancelled'],
  };
  const [cls, label] = map[s] || ['pending', s];
  return `<span class="badge ${cls}">${label}</span>`;
}

function renderTable(rows) {
  const tbody = document.getElementById('po-tbody');
  document.getElementById('row-count').textContent = `${rows.length} order${rows.length !== 1 ? 's' : ''}`;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="11" style="padding:28px;text-align:center;
        color:var(--text-muted);">No purchase orders match current filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(p => {
    const items = Array.isArray(p.line_items) ? p.line_items : [];
    const hasDev = deviationPOs.has(p.id);
    const devCell = hasDev
      ? `<a href="/deviations" style="text-decoration:none;">
           <span class="badge high" style="cursor:pointer;">⚠ Active</span>
         </a>`
      : `<span style="color:var(--text-muted);font-size:11px;">—</span>`;

    return `<tr ${hasDev ? 'style="background:color-mix(in srgb, var(--critical) 5%, transparent);"' : ''}>
      <td class="mono">${p.id}</td>
      <td style="max-width:180px;" class="truncate" title="${p.supplier_name || '—'}">${p.supplier_name || '—'}</td>
      <td>${statusBadge(p.status)}</td>
      <td class="mono">${fmt(p.total_value_usd)}</td>
      <td class="mono">${p.currency}</td>
      <td class="mono">${p.incoterm}</td>
      <td class="mono" style="font-size:10px;white-space:nowrap;">${fmtDate(p.created_date)}</td>
      <td class="mono" style="font-size:10px;white-space:nowrap;">${fmtDate(p.expected_delivery)}</td>
      <td class="mono" style="font-size:10px;white-space:nowrap;">${fmtDate(p.actual_delivery)}</td>
      <td class="mono">${items.length}</td>
      <td>${devCell}</td>
    </tr>`;
  }).join('');
}

function applyFilters() {
  const search = document.getElementById('search-input').value.toLowerCase().trim();
  let rows = allPOs;

  if (activeStatus) {
    rows = rows.filter(p => p.status === activeStatus);
  }
  if (search) {
    rows = rows.filter(p =>
      p.id.toLowerCase().includes(search) ||
      (p.supplier_name || '').toLowerCase().includes(search)
    );
  }
  renderTable(rows);
}

function setStatus(status, el) {
  activeStatus = status;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  const labels = { '': 'All Purchase Orders', in_transit: 'In Transit', confirmed: 'Confirmed', processing: 'Processing', delivered: 'Delivered' };
  document.getElementById('table-label').textContent = labels[status] || 'Purchase Orders';
  applyFilters();
}

async function loadPOs() {
  try {
    // Load all POs (limit 350 — full dataset) and active deviations in parallel
    const source = document.getElementById('source-filter').value;
    const [pos, devs] = await Promise.all([
      fetch(`/api/purchase-orders?limit=350&source=${source}`).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
      fetch(`/api/deviations?resolved=0&limit=1000&source=${source}`).then(r => r.json()),
    ]);

    // Build set of PO IDs with active deviations
    deviationPOs = new Set();
    devs.forEach(d => deviationPOs.add(d.po_id));

    allPOs = pos;

    // Summary counts
    document.getElementById('m-transit').textContent    = pos.filter(p => p.status === 'in_transit').length;
    document.getElementById('m-confirmed').textContent  = pos.filter(p => p.status === 'confirmed').length;
    document.getElementById('m-processing').textContent = pos.filter(p => p.status === 'processing').length;
    document.getElementById('m-delivered').textContent  = pos.filter(p => p.status === 'delivered').length;

    applyFilters();
  } catch (err) {
    document.getElementById('po-tbody').innerHTML =
      `<tr><td colspan="11" style="padding:28px;text-align:center;color:var(--critical);">
        Failed to load purchase orders: ${err.message}</td></tr>`;
  }
}

loadPOs();
