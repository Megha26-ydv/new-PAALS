/* action_centre.js — recommendation review and approval workflow */

function fmt(v) {
  if (!v && v !== 0) return '—';
  if (v >= 1000000) return `$${(v / 1000000).toFixed(2)}M`;
  if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`;
  return `$${Number(v).toFixed(0)}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

function devTypeLabel(t) {
  return t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function parseAlts(raw) {
  try { return JSON.parse(raw || '[]'); } catch (e) { return []; }
}

function renderRecommendation(r) {
  const alts = parseAlts(r.alternative_suppliers);

  return `
  <div class="card mb-16">
    <div class="card-header">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span class="text-mono" style="color:var(--text-primary);">${r.id}</span>
        <span class="badge ${r.severity}">${r.severity}</span>
        <span class="badge ${r.status}">${r.status.toUpperCase()}</span>
        ${r.requires_approval ? '<span class="badge pending" style="font-size:9px;">APPROVAL REQ</span>' : ''}
      </div>
      <span style="font-size:11px;color:var(--text-muted);white-space:nowrap;">${fmtDate(r.created_at)}</span>
    </div>

    <div class="rec-grid-3" style="padding:14px 16px;display:grid;grid-template-columns:1fr 1fr 320px;gap:20px;">

      <!-- Deviation context -->
      <div>
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.06em;
                    color:var(--text-muted);margin-bottom:8px;">Deviation Context</div>
        <div class="detail-row">
          <span class="detail-label">Deviation ID</span>
          <span class="detail-value mono">${r.deviation_id}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Type</span>
          <span class="detail-value">${devTypeLabel(r.deviation_type)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">PO Reference</span>
          <span class="detail-value mono">${r.po_id}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Supplier</span>
          <span class="detail-value" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;">
            ${r.supplier_name}
          </span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Exposure</span>
          <span class="detail-value mono text-critical">${fmt(r.financial_exposure_usd)}</span>
        </div>
      </div>

      <!-- Agent recommendation -->
      <div>
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.06em;
                    color:var(--text-muted);margin-bottom:8px;">Agent Recommendation</div>
        <div class="detail-row">
          <span class="detail-label">Action</span>
          <span class="detail-value mono" style="font-size:10px;">${r.action}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Cost Impact</span>
          <span class="detail-value mono">${fmt(r.estimated_cost_impact_usd)}</span>
        </div>

        ${alts.length ? `
        <div style="margin-top:8px;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px;">Alternative Suppliers</div>
          ${alts.map(a => `<div style="font-size:11px;color:var(--text-secondary);padding:2px 0;">· ${a}</div>`).join('')}
        </div>` : ''}

        <div class="reasoning-block" style="margin-top:10px;font-size:11px;">${r.reasoning}</div>
      </div>

      <!-- Communication + action buttons -->
      <div>
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.06em;
                    color:var(--text-muted);margin-bottom:8px;">
          ${r.draft_communication ? 'Draft Communication' : 'Execution'}
        </div>

        ${r.draft_communication ? `
        <div class="comm-draft" style="max-height:150px;">${r.draft_communication}</div>` : ''}

        ${r.status === 'pending' ? `
        <div style="display:flex;gap:8px;margin-top:12px;">
          <button class="btn btn-approve" style="flex:1;" onclick="approve('${r.id}')">✓ Approve</button>
          <button class="btn btn-reject" style="flex:1;" onclick="reject('${r.id}')">✗ Reject</button>
        </div>
        <div style="margin-top:8px;">
          <a href="/deviations/${r.deviation_id}" class="btn btn-ghost w-full btn-sm">
            View Deviation →
          </a>
        </div>` : `
        <div class="detail-row" style="margin-top:8px;">
          <span class="detail-label">${r.status === 'approved' ? 'Approved by' : 'Rejected at'}</span>
          <span class="detail-value">${r.approved_by || fmtDate(r.executed_at)}</span>
        </div>
        <div style="margin-top:8px;">
          <a href="/deviations/${r.deviation_id}" class="btn btn-ghost w-full btn-sm">
            View Deviation →
          </a>
        </div>`}
      </div>
    </div>
  </div>`;
}

async function loadRecs(status, tabEl) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  if (tabEl) tabEl.classList.add('active');

  const container = document.getElementById('recs-container');
  container.innerHTML = `<div style="padding:28px;text-align:center;color:var(--text-muted);">
    Loading…</div>`;

  try {
    const recs = await fetch(`/api/recommendations?status=${status}`).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });

    if (!recs.length) {
      const hint = status === 'pending'
        ? '<br><span style="font-size:11px;">Open a deviation and run agent analysis to generate recommendations.</span>'
        : '';
      container.innerHTML = `<div class="card"><div style="padding:36px;text-align:center;
          color:var(--text-muted);font-size:13px;">
        No ${status} recommendations.${hint}</div></div>`;
      return;
    }

    container.innerHTML = recs.map(renderRecommendation).join('');
  } catch (err) {
    container.innerHTML = `<div class="alert warning">
      <span>⚠</span><span>Failed to load recommendations: ${err.message}</span>
    </div>`;
  }
}

async function approve(id) {
  try {
    const r = await fetch(`/api/recommendations/${id}/approve`, { method: 'POST' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await loadRecs('pending');
  } catch (err) {
    alert(`Approval failed: ${err.message}`);
  }
}

async function reject(id) {
  try {
    const r = await fetch(`/api/recommendations/${id}/reject`, { method: 'POST' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await loadRecs('pending');
  } catch (err) {
    alert(`Rejection failed: ${err.message}`);
  }
}

loadRecs('pending');
