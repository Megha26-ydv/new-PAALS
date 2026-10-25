/* deviation_detail.js — loaded by deviation_detail.html
   DEV_ID is set as a global const by the template before this file loads. */

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

function renderRec(r) {
  const alts = parseAlts(r.alternative_suppliers);
  const costImpact = r.estimated_cost_impact_usd ? fmt(r.estimated_cost_impact_usd) : '—';

  return `
    <div class="card" style="margin-bottom:12px;">
      <div class="card-header">
        <div style="display:flex;align-items:center;gap:8px;">
          <span class="text-mono" style="color:var(--text-primary);font-size:12px;">${r.id}</span>
          <span class="badge ${r.status}">${r.status.toUpperCase()}</span>
          ${r.requires_approval ? '<span class="badge pending" style="font-size:9px;">APPROVAL REQ</span>' : ''}
        </div>
        <span style="font-size:10px;color:var(--text-muted);">${fmtDate(r.created_at)}</span>
      </div>
      <div class="card-body">
        <div class="detail-row">
          <span class="detail-label">Action</span>
          <span class="detail-value" style="font-family:var(--font-mono);font-size:11px;">${r.action}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Requires Approval</span>
          <span class="detail-value">${r.requires_approval
            ? '<span class="text-high">Yes</span>'
            : '<span class="text-low">No</span>'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Cost Impact Est.</span>
          <span class="detail-value mono">${costImpact}</span>
        </div>

        <div style="margin:12px 0 4px;">
          <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;
                      letter-spacing:0.06em;margin-bottom:6px;">Agent Reasoning</div>
          <div class="reasoning-block">${r.reasoning}</div>
        </div>

        ${alts.length ? `
        <div style="margin:10px 0 4px;">
          <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;
                      letter-spacing:0.06em;margin-bottom:6px;">Alternative Suppliers Identified</div>
          ${alts.map(a => `
            <div style="display:flex;align-items:center;gap:8px;padding:5px 0;
                        border-bottom:1px solid var(--border);font-size:12px;color:var(--text-secondary);">
              <span style="color:var(--accent-blue);">◆</span> ${a}
            </div>`).join('')}
        </div>` : ''}

        ${r.draft_communication ? `
        <div style="margin:12px 0 4px;">
          <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;
                      letter-spacing:0.06em;margin-bottom:6px;">Draft Communication</div>
          <div class="comm-draft">${r.draft_communication}</div>
        </div>` : ''}

        ${r.status === 'pending' ? `
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-approve" style="flex:1;" onclick="approveRec('${r.id}')">✓ Approve</button>
          <button class="btn btn-reject" style="flex:1;" onclick="rejectRec('${r.id}')">✗ Reject</button>
        </div>` : r.status === 'approved' ? `
        <div class="detail-row" style="margin-top:10px;">
          <span class="detail-label">Approved by</span>
          <span class="detail-value">${r.approved_by || '—'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Executed at</span>
          <span class="detail-value">${fmtDate(r.executed_at)}</span>
        </div>` : `
        <div class="detail-row" style="margin-top:10px;">
          <span class="detail-label">Rejected at</span>
          <span class="detail-value">${fmtDate(r.executed_at)}</span>
        </div>`}
      </div>
    </div>`;
}

function renderAgentPanel(d) {
  const recs = d.recommendations || [];
  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Agent Analysis</span>
        <span class="badge ${d.agent_activated ? 'approved' : 'pending'}">
          ${d.agent_activated ? 'ACTIVE' : 'IDLE'}
        </span>
      </div>
      <div class="card-body">
        ${recs.length
          ? `<p style="font-size:12px;color:var(--text-muted);margin-bottom:10px;">
               ${recs.length} recommendation${recs.length !== 1 ? 's' : ''} generated.
             </p>`
          : `<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">
               No agent analysis has run for this deviation yet.
             </p>`}
        <button class="btn btn-primary w-full" onclick="runAgent('${d.id}')">
          ${recs.length ? '↺ Re-run Analysis' : '▶ Run Agent Analysis'}
        </button>
        <div id="agent-status" style="margin-top:8px;"></div>
      </div>
    </div>
    <div id="recommendations-panel" style="margin-top:12px;">
      ${recs.map(renderRec).join('')}
    </div>`;
}

function renderDeviationCard(d) {
  const po = d.purchase_order || {};
  return `
    <div class="card mb-16">
      <div class="card-header">
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="text-mono" style="font-size:13px;color:var(--text-primary);">${d.id}</span>
          <span class="badge ${d.severity}">${d.severity}</span>
          ${d.resolved ? '<span class="badge approved">RESOLVED</span>' : ''}
        </div>
        <span style="font-size:11px;color:var(--text-muted);">${fmtDate(d.detected_at)}</span>
      </div>
      <div class="card-body">
        <div class="detail-row">
          <span class="detail-label">Deviation Type</span>
          <span class="detail-value">${devTypeLabel(d.deviation_type)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Purchase Order</span>
          <span class="detail-value mono">${d.po_id}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Supplier</span>
          <span class="detail-value">${d.supplier_name}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Country · Port</span>
          <span class="detail-value">${d.supplier_country || '—'} · ${d.port_of_origin || '—'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Supplier Tier</span>
          <span class="detail-value">Tier ${d.strategic_tier}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Reliability Score</span>
          <span class="detail-value">
            ${d.reliability_score ? `${(d.reliability_score * 100).toFixed(0)}%` : '—'}
          </span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Annual Spend</span>
          <span class="detail-value mono">${d.annual_spend_usd ? fmt(d.annual_spend_usd) : '—'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Financial Exposure</span>
          <span class="detail-value text-critical" style="font-family:var(--font-mono);">
            ${fmt(d.financial_exposure_usd)}
          </span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Delay (days)</span>
          <span class="detail-value">${d.delay_days ?? '—'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Customers Affected</span>
          <span class="detail-value">${d.affected_customers.length}</span>
        </div>
      </div>
    </div>

    <div class="card mb-16">
      <div class="card-header"><span class="card-title">Event Description</span></div>
      <div class="card-body">
        <p style="font-size:13px;color:var(--text-secondary);line-height:1.65;">${d.description}</p>
      </div>
    </div>

    ${po.id ? `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Purchase Order</span>
        <span class="text-mono" style="font-size:11px;color:var(--text-muted);">${po.id}</span>
      </div>
      <div class="card-body">
        <div class="detail-row">
          <span class="detail-label">Total Value</span>
          <span class="detail-value mono">${fmt(po.total_value_usd)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Status</span>
          <span class="detail-value">${po.status}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Expected Delivery</span>
          <span class="detail-value">${fmtDate(po.expected_delivery)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Actual Delivery</span>
          <span class="detail-value">${po.actual_delivery ? fmtDate(po.actual_delivery)
            : po.status === 'cancelled' ? '<span class="badge rejected">Cancelled</span>'
            : '<span class="badge pending">In Transit</span>'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Incoterm</span>
          <span class="detail-value mono">${po.incoterm || '—'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Currency</span>
          <span class="detail-value mono">${po.currency || '—'}</span>
        </div>
      </div>
    </div>` : ''}`;
}

async function loadDeviation() {
  const container = document.getElementById('dev-container');
  try {
    const r = await fetch(`/api/deviations/${DEV_ID}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();

    container.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 340px;gap:16px;">
        <div>${renderDeviationCard(d)}</div>
        <div>${renderAgentPanel(d)}</div>
      </div>`;
  } catch (err) {
    container.innerHTML = `
      <div class="alert warning">
        <span>⚠</span>
        <span>Failed to load deviation ${DEV_ID}: ${err.message}</span>
      </div>`;
  }
}

async function runAgent(devId) {
  const statusEl = document.getElementById('agent-status');
  const btn = document.querySelector('.btn-primary');
  if (btn) { btn.disabled = true; btn.textContent = '⟳ Processing…'; }
  statusEl.innerHTML = `<div class="alert info" style="margin-top:8px;">
    <span>◈</span><span>Agent evaluating deviation…</span>
  </div>`;

  try {
    const r = await fetch(`/api/deviations/${devId}/run-agent`, { method: 'POST' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const result = await r.json();

    statusEl.innerHTML = `<div class="alert info" style="margin-top:8px;background:var(--low-dim);
        border-color:color-mix(in srgb, var(--approved) 35%, transparent);color:var(--approved);">
      <span>✓</span>
      <span>Recommendation <strong>${result.recommendation_id}</strong> generated —
            action: <span style="font-family:var(--font-mono);">${result.action}</span></span>
    </div>`;

    // Reload full deviation view to show the new recommendation
    setTimeout(loadDeviation, 600);
  } catch (err) {
    statusEl.innerHTML = `<div class="alert warning" style="margin-top:8px;">
      <span>⚠</span><span>Agent execution failed: ${err.message}</span>
    </div>`;
    if (btn) { btn.disabled = false; btn.textContent = '▶ Run Agent Analysis'; }
  }
}

async function approveRec(recId) {
  try {
    const r = await fetch(`/api/recommendations/${recId}/approve`, { method: 'POST' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await loadDeviation();
  } catch (err) {
    alert(`Approval failed: ${err.message}`);
  }
}

async function rejectRec(recId) {
  try {
    const r = await fetch(`/api/recommendations/${recId}/reject`, { method: 'POST' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await loadDeviation();
  } catch (err) {
    alert(`Rejection failed: ${err.message}`);
  }
}

loadDeviation();
