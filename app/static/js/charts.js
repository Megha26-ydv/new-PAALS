/* charts.js — dashboard charts (D3 v7): smooth trend area chart with dataset switch, severity donut.
   Exposes initTrendChart() and renderSeverityDonut(dist) for dashboard.js. */

const CHART_REDUCE = matchMedia('(prefers-reduced-motion: reduce)').matches;
const CHART_EASE = d3.easeCubicOut;
const dur = ms => (CHART_REDUCE ? 0 : ms);
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function fmtMoney(v) {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${Math.round(v)}`;
}

// ── Trend chart ──────────────────────────────────────────────────────────────
const TREND_SOURCES = {
  dataco: { url: '/api/kaggle/insights', title: 'Sales analytics · DataCo', unit: 'sales' },
  scms:   { url: '/api/kaggle/scms/insights', title: 'Shipment analytics · USAID SCMS', unit: 'commodity value' },
};
const trendCache = {};
let trendSource = 'dataco';

async function trendData(src) {
  if (!trendCache[src]) {
    const res = await fetch(TREND_SOURCES[src].url).then(r => r.json());
    trendCache[src] = res.imported
      ? res.monthly.filter(m => m.month).map(m => ({
          date: new Date(m.month + '-01T00:00:00'), value: m.value_usd || 0, late: m.late_rate || 0, orders: m.orders,
        }))
      : [];
  }
  return trendCache[src];
}

function initTrendChart() {
  const seg = document.getElementById('trend-seg');
  if (!seg) return;
  const pill = seg.querySelector('.seg-pill');
  const placePill = () => {
    const on = seg.querySelector('button.on');
    pill.style.width = on.offsetWidth + 'px';
    pill.style.transform = `translateX(${on.offsetLeft - 4}px)`;
  };
  placePill();
  document.fonts && document.fonts.ready.then(placePill);

  seg.addEventListener('click', e => {
    const b = e.target.closest('button[data-src]');
    if (!b || b.classList.contains('on')) return;
    seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    placePill();
    trendSource = b.dataset.src;
    drawTrend(true);
  });

  let t;
  addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => { placePill(); drawTrend(false, true); }, 150); });
  drawTrend(false);
}

async function drawTrend(switching, resizing) {
  const wrap = document.getElementById('trend-chart');
  const tip = document.getElementById('trend-tip');
  const meta = TREND_SOURCES[trendSource];
  let data;
  try {
    data = await trendData(trendSource);
  } catch (err) {
    console.error('Trend chart data failed:', err);
    wrap.classList.remove('loading');
    document.getElementById('trend-kpi').textContent = '—';
    document.getElementById('trend-sub').textContent = 'Could not load chart data — refresh to retry';
    return;
  }
  wrap.classList.remove('loading');
  document.getElementById('trend-title').textContent = meta.title;

  const old = d3.select(wrap).select('svg');
  if (!old.empty()) {
    if (switching) await old.transition().duration(dur(260)).ease(d3.easeCubicIn).style('opacity', 0).end().catch(() => {});
    old.remove();
  }
  if (!data.length) {
    document.getElementById('trend-kpi').textContent = '—';
    document.getElementById('trend-sub').textContent = 'Dataset not imported yet';
    return;
  }

  // KPI: last 12 months vs the 12 before
  const last = data.slice(-12), prev = data.slice(-24, -12);
  const sum = a => a.reduce((s, d) => s + d.value, 0);
  const cur = sum(last), before = sum(prev);
  const change = before ? (cur - before) / before : 0;
  animateText(document.getElementById('trend-kpi'), cur, fmtMoney, resizing ? 0 : 1000);
  document.getElementById('trend-sub').innerHTML =
    `${meta.unit} in the last 12 months of data · <b>${change >= 0 ? '▲' : '▼'} ${Math.abs(change * 100).toFixed(1)}%</b> vs prior year`;

  const W = wrap.clientWidth, H = wrap.clientHeight;
  const m = { t: 12, r: 46, b: 26, l: 54 };
  const x = d3.scaleTime().domain(d3.extent(data, d => d.date)).range([m.l, W - m.r]);
  const y = d3.scaleLinear().domain([0, d3.max(data, d => d.value) * 1.12]).nice().range([H - m.b, m.t]);
  const y2 = d3.scaleLinear().domain([0, Math.max(0.2, d3.max(data, d => d.late) * 1.15)]).range([H - m.b, m.t]);

  const green = cssVar('--accent-blue'), orange = cssVar('--high');
  const svg = d3.select(wrap).insert('svg', ':first-child').attr('viewBox', `0 0 ${W} ${H}`);
  const uid = 'tr' + Math.random().toString(36).slice(2, 7);

  const defs = svg.append('defs');
  const grad = defs.append('linearGradient').attr('id', uid + 'g').attr('x1', 0).attr('x2', 0).attr('y1', 0).attr('y2', 1);
  grad.append('stop').attr('offset', '0%').attr('stop-color', green).attr('stop-opacity', .28);
  grad.append('stop').attr('offset', '100%').attr('stop-color', green).attr('stop-opacity', 0);
  const clip = defs.append('clipPath').attr('id', uid + 'c').append('rect')
    .attr('x', 0).attr('y', 0).attr('height', H).attr('width', resizing ? W : 0);

  // Grid + axes
  svg.append('g').selectAll('line').data(y.ticks(4)).join('line')
    .attr('class', 'chart-gridline').attr('x1', m.l).attr('x2', W - m.r).attr('y1', d => y(d)).attr('y2', d => y(d));
  svg.append('g').attr('class', 'chart-axis').attr('transform', `translate(0,${H - m.b + 6})`)
    .call(d3.axisBottom(x).ticks(W < 500 ? 4 : 7).tickSize(0).tickFormat(d3.timeFormat(data.length > 60 ? '%Y' : "%b '%y")));
  svg.append('g').attr('class', 'chart-axis').attr('transform', `translate(${m.l - 8},0)`)
    .call(d3.axisLeft(y).ticks(4).tickSize(0).tickFormat(fmtMoney));
  svg.append('g').attr('class', 'chart-axis').attr('transform', `translate(${W - m.r + 8},0)`)
    .call(d3.axisRight(y2).ticks(4).tickSize(0).tickFormat(d3.format('.0%')));

  // Series
  const plot = svg.append('g').attr('clip-path', `url(#${uid}c)`);
  const area = d3.area().curve(d3.curveMonotoneX).x(d => x(d.date)).y0(H - m.b).y1(d => y(d.value));
  const line = d3.line().curve(d3.curveMonotoneX).x(d => x(d.date)).y(d => y(d.value));
  const lateLine = d3.line().curve(d3.curveMonotoneX).x(d => x(d.date)).y(d => y2(d.late));
  plot.append('path').datum(data).attr('d', area).attr('fill', `url(#${uid}g)`);
  plot.append('path').datum(data).attr('d', lateLine).attr('fill', 'none').attr('stroke', orange)
    .attr('stroke-width', 1.8).attr('stroke-opacity', .85).attr('stroke-linecap', 'round');
  plot.append('path').datum(data).attr('d', line).attr('fill', 'none').attr('stroke', green)
    .attr('stroke-width', 2.6).attr('stroke-linecap', 'round');

  // Draw-in: reveal left to right
  if (!resizing) clip.transition().duration(dur(1400)).ease(d3.easeCubicInOut).attr('width', W);
  if (switching) svg.style('opacity', 0).transition().duration(dur(350)).style('opacity', 1);

  // Hover: guide line, dots, tooltip
  const guide = svg.append('line').attr('y1', m.t).attr('y2', H - m.b)
    .attr('stroke', cssVar('--border-light')).attr('stroke-width', 1).style('opacity', 0);
  const dot = svg.append('circle').attr('r', 5).attr('fill', '#fff').attr('stroke', green).attr('stroke-width', 2.5).style('opacity', 0);
  const dot2 = svg.append('circle').attr('r', 4).attr('fill', '#fff').attr('stroke', orange).attr('stroke-width', 2).style('opacity', 0);
  const bisect = d3.bisector(d => d.date).center;
  const fmtMonth = d3.timeFormat('%B %Y');

  svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', W - m.l - m.r).attr('height', H - m.t - m.b)
    .attr('fill', 'transparent')
    .on('pointermove', e => {
      const [px] = d3.pointer(e);
      const d = data[bisect(data, x.invert(px))];
      const cx = x(d.date);
      guide.attr('x1', cx).attr('x2', cx).style('opacity', 1);
      dot.attr('cx', cx).attr('cy', y(d.value)).style('opacity', 1);
      dot2.attr('cx', cx).attr('cy', y2(d.late)).style('opacity', 1);
      tip.innerHTML = `<div class="muted">${fmtMonth(d.date)}</div><b>${fmtMoney(d.value)}</b>
        <div>${d.orders.toLocaleString()} orders · <span style="color:#f7b27a">${(d.late * 100).toFixed(1)}% late</span></div>`;
      const tw = tip.offsetWidth;
      const left = cx + 14 + tw > W ? cx - tw - 14 : cx + 14;
      tip.style.left = left + 'px';
      tip.style.top = Math.max(0, y(d.value) - 30) + 'px';
      tip.classList.add('on');
    })
    .on('pointerleave', () => {
      [guide, dot, dot2].forEach(s => s.style('opacity', 0));
      tip.classList.remove('on');
    });
}

function animateText(el, target, fmt, ms) {
  const from = el._v || 0;
  el._v = target;
  if (!ms || CHART_REDUCE) { el.textContent = fmt(target); return; }
  d3.select(el).transition().duration(ms).ease(CHART_EASE)
    .tween('text', () => { const i = d3.interpolateNumber(from, target); return t => { el.textContent = fmt(i(t)); }; });
}

// ── Severity donut ───────────────────────────────────────────────────────────
const SEV_ORDER = ['critical', 'high', 'medium', 'low'];
let donutState = null;

function renderSeverityDonut(dist) {
  const host = document.getElementById('sev-donut');
  if (!host) return;
  const data = SEV_ORDER.map(k => ({ key: k, value: dist[k] || 0 }));
  const total = d3.sum(data, d => d.value);
  animateText(document.getElementById('donut-n'), total, v => Math.round(v).toLocaleString(), 1000);

  const R = 100, r = 72;
  const pie = d3.pie().value(d => d.value).sort(null).padAngle(.025);
  const arc = d3.arc().innerRadius(r).outerRadius(R).cornerRadius(7);
  const colors = Object.fromEntries(SEV_ORDER.map(k => [k, cssVar('--' + k)]));

  if (!donutState) {
    const svg = d3.select(host).insert('svg', ':first-child').attr('viewBox', `${-R - 6} ${-R - 6} ${2 * R + 12} ${2 * R + 12}`);
    svg.append('circle').attr('r', (R + r) / 2).attr('fill', 'none')
      .attr('stroke', cssVar('--bg-raised')).attr('stroke-width', R - r);
    donutState = { g: svg.append('g') };
  }

  const arcs = pie(data);
  const paths = donutState.g.selectAll('path').data(arcs, d => d.data.key);
  const entering = paths.enter().append('path')
    .attr('class', 'donut-arc').attr('fill', d => colors[d.data.key])
    .each(function (d) { this._cur = { startAngle: d.startAngle, endAngle: d.startAngle }; })
    .on('pointerenter', (e, d) => highlight(d.data.key))
    .on('pointerleave', () => highlight(null));

  entering.merge(paths)
    .transition().duration(dur(1100)).delay((d, i) => (paths.empty() ? i * 90 : 0)).ease(CHART_EASE)
    .attrTween('d', function (d) {
      const i = d3.interpolate(this._cur, d);
      this._cur = i(1);
      return t => arc(i(t));
    });

  document.getElementById('donut-list').innerHTML = data.map(d => `
    <div data-key="${d.key}"><i style="background:${colors[d.key]}"></i>${d.key[0].toUpperCase() + d.key.slice(1)}
      <span class="text-muted" style="font-size:11px;">${total ? (d.value / total * 100).toFixed(0) : 0}%</span><b>${d.value.toLocaleString()}</b></div>`).join('');
  document.querySelectorAll('#donut-list [data-key]').forEach(el => {
    el.addEventListener('pointerenter', () => highlight(el.dataset.key));
    el.addEventListener('pointerleave', () => highlight(null));
  });

  function highlight(key) {
    donutState.g.selectAll('path')
      .classed('dim', d => key && d.data.key !== key)
      .classed('hl', d => d.data.key === key);
    document.querySelectorAll('#donut-list [data-key]').forEach(el => el.classList.toggle('hl', el.dataset.key === key));
  }
}
