/* Dashboard: loads metrics, renders deviations table, manages WebSocket event feed */

const MAX_FEED_ITEMS = 60;

function formatCurrency(val) {
  if (val >= 1000000) return `${(val/1000000).toFixed(2)}M`;
  if (val >= 1000) return `${(val/1000).toFixed(0)}K`;
  return val.toFixed(0);
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day:'2-digit', month:'short' }) +
    ' ' + d.toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' });
}

function devTypeLabel(t) {
  return t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function severityBadge(s) {
  return `<span class="badge ${s}">${s}</span>`;
}

async function loadMetrics() {
  let data;
  try {
    const r = await fetch('/api/dashboard');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    data = await r.json();
  } catch (err) {
    console.error('Dashboard metrics failed:', err);
    ['m-deviations','m-approvals','m-exposure','m-actions'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
    document.getElementById('m-dev-sub').textContent = 'Could not reach the server — retrying';
    return;
  }

  const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  setText('m-deviations', data.active_deviations);
  setText('m-dev-sub', `${data.severity_distribution?.critical || 0} critical · ${data.severity_distribution?.high || 0} high`);
  setText('m-approvals', data.pending_approvals);
  setText('m-exposure', formatCurrency(data.financial_exposure_usd));
  setText('m-actions', data.agent_actions_today);

  // Each panel renders on its own: one failing panel must not blank the rest of the dashboard
  const panels = [
    ['region risk', () => renderRegionRisk(data.supplier_risk_by_region || [])],
    ['deviation types', () => renderDeviationTypes(data.deviation_types || [])],
    ['severity donut', () => renderSeverityDonut(data.severity_distribution || {})],
  ];
  for (const [name, render] of panels) {
    try { render(); } catch (err) { console.error(`Dashboard panel "${name}" failed:`, err); }
  }
}

function renderRegionRisk(regions) {
  const el = document.getElementById('risk-region');
  if (!regions.length) { el.innerHTML = '<p style="color:var(--text-muted);font-size:12px;padding:8px;">No data</p>'; return; }

  const maxExp = Math.max(...regions.map(r => r.total_exposure || 0));
  el.innerHTML = regions.map(r => {
    const exposure = r.total_exposure || 0;
    const pct = maxExp > 0 ? (exposure / maxExp * 100) : 0;
    const devs = r.deviation_count || 0;
    const rel = r.avg_reliability ? (r.avg_reliability * 100).toFixed(0) : '—';
    return `
      <div style="padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
          <span style="font-size:12px;color:var(--text-primary);">${r.region}</span>
          <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);">
            $${formatCurrency(exposure)} · ${devs} dev${devs !== 1 ? 's' : ''}
          </span>
        </div>
        <div style="background:var(--bg-raised);border-radius:2px;height:4px;overflow:hidden;">
          <div style="background:${devs > 3 ? 'var(--critical)' : devs > 1 ? 'var(--high)' : 'var(--low)'};
                      width:${pct}%;height:100%;border-radius:2px;transition:width 0.6s;"></div>
        </div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:3px;">
          Avg reliability: ${rel}%
        </div>
      </div>
    `;
  }).join('');
}

function renderDeviationTypes(types) {
  const el = document.getElementById('dev-type-breakdown');
  const maxExp = Math.max(...types.map(t => t.exposure || 0));
  el.innerHTML = types.slice(0, 6).map(t => {
    const pct = maxExp > 0 ? (t.exposure / maxExp * 100) : 0;
    return `
      <div style="padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
          <span style="font-size:12px;color:var(--text-secondary);">${devTypeLabel(t.deviation_type)}</span>
          <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);">
            ${t.cnt} · $${formatCurrency(t.exposure)}
          </span>
        </div>
        <div style="background:var(--bg-raised);border-radius:2px;height:3px;overflow:hidden;">
          <div style="background:var(--accent-blue);width:${pct}%;height:100%;border-radius:2px;"></div>
        </div>
      </div>
    `;
  }).join('');
}


async function loadDeviations() {
  const tbody = document.getElementById('deviations-tbody');
  try {
    const r = await fetch('/api/deviations?limit=10');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const rows = await r.json();

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="padding:20px;text-align:center;color:var(--text-muted);">No active deviations</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(d => `
      <tr>
        <td class="mono">${d.id}</td>
        <td>${devTypeLabel(d.deviation_type)}</td>
        <td style="max-width:180px;" class="truncate" title="${d.supplier_name}">${d.supplier_name}</td>
        <td>${severityBadge(d.severity)}</td>
        <td class="mono">$${formatCurrency(d.financial_exposure_usd)}</td>
        <td class="mono">${d.affected_customers.length}</td>
        <td class="mono" style="font-size:10px;">${formatDate(d.detected_at)}</td>
        <td>${d.agent_activated ? '<span class="badge approved">Active</span>' : '<span class="badge pending">Pending</span>'}</td>
        <td><a href="/deviations/${d.id}" class="btn btn-ghost btn-sm">Detail →</a></td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:var(--critical);">
      Failed to load deviations: ${err.message}</td></tr>`;
  }
}

// WebSocket event feed
function initEventFeed() {
  const feed = document.getElementById('event-feed');
  const statusEl = document.getElementById('feed-status');
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  let ws;
  let reconnectTimer;

  function connect() {
    ws = new WebSocket(`${protocol}://${location.host}/ws/events`);

    ws.onopen = () => {
      statusEl.textContent = 'LIVE';
      statusEl.className = 'badge approved';
      feed.innerHTML = ''; // Clear connecting message
    };

    ws.onmessage = (evt) => {
      const payload = JSON.parse(evt.data);
      if (!payload.event) return;
      prependEvent(payload.event);
      pulsePipelineStep(payload.event.type);
      // Refresh metrics when agent activity occurs
      if (['agent_activated','approved','rejected','resolved'].includes(payload.event.type)) {
        loadMetrics();
        loadDeviations();
      }
    };

    ws.onclose = () => {
      statusEl.textContent = 'RECONNECTING';
      statusEl.className = 'badge pending';
      reconnectTimer = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();
  }

  function prependEvent(ev) {
    const item = document.createElement('div');
    item.className = 'event-item';
    const time = new Date(ev.timestamp).toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    item.innerHTML = `
      <span class="event-icon">${ev.icon || '·'}</span>
      <div class="event-body">
        <div class="event-message">${ev.message}</div>
        <div class="event-time">${time} UTC</div>
      </div>
    `;
    feed.insertBefore(item, feed.firstChild);

    // Trim old events
    while (feed.children.length > MAX_FEED_ITEMS) {
      feed.removeChild(feed.lastChild);
    }
  }

  // Load recent events first
  fetch('/api/events?limit=15').then(r => r.json()).then(events => {
    feed.innerHTML = '';
    events.reverse().forEach(ev => prependEvent({
      icon: '◈',
      message: ev.message,
      timestamp: ev.timestamp,
    }));
  }).catch(() => {});

  connect();
}

// Pulse the relevant pipeline step based on event type
const EVENT_STEP_MAP = {
  deviation_detected:    0,
  agent_activated:       2,
  alternative_evaluated: 4,
  communication_drafted: 4,
  escalated:             5,
  approved:              6,
  rejected:              5,
  resolved:              6,
  shipment_update:       1,
  quality_hold:          3,
};

function pulsePipelineStep(eventType) {
  const stepIndex = EVENT_STEP_MAP[eventType];
  if (stepIndex === undefined) return;
  const steps = document.querySelectorAll('.flow-step');
  if (!steps[stepIndex]) return;

  // Clear previous pulses
  steps.forEach(s => s.classList.remove('active'));
  steps[stepIndex].classList.add('active');

  // Return to "Deviation Detected" as baseline after a delay
  setTimeout(() => {
    steps.forEach(s => s.classList.remove('active'));
    if (steps[0]) steps[0].classList.add('active');
  }, 3500);
}

// Init
loadMetrics();
loadDeviations();
initEventFeed();
if (typeof initTrendChart === 'function') initTrendChart();

// Refresh metrics every 60s
setInterval(loadMetrics, 60000);
setInterval(loadDeviations, 60000);
