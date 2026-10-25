/* digital_twin.js — D3 v7 force-directed supply chain dependency graph
   Globals exposed for button onclick handlers: resetZoom, reloadGraph */

// Module state — kept at file scope so resetZoom can reference them
let _svg = null;
let _zoomBehaviour = null;

function nodeColor(d) {
  if (d.type === 'supplier') return d.tier === 1 ? '#3e7230' : '#86b86c';
  if (d.type === 'po') return d.has_deviation ? '#dc5643' : '#b9c7ad';
  if (d.type === 'customer_order') return '#c4e0a8';
  if (d.type === 'customer') return '#c99a1f';
  return '#8c9785';
}

function nodeRadius(d) {
  if (d.type === 'supplier') return d.tier === 1 ? 9 : 7;
  if (d.type === 'po') return d.has_deviation ? 6 : 4;
  if (d.type === 'customer_order') return 3;
  if (d.type === 'customer') return 8;
  return 4;
}

function tooltipHtml(d) {
  const rows = [`<strong>${d.label}</strong>`, `<span style="color:#8c9785;">Type: ${d.type}</span>`];

  if (d.type === 'supplier') {
    rows.push(`Country: ${d.country}`, `Tier: ${d.tier}`,
      `Reliability: ${(d.reliability * 100).toFixed(0)}%`);
  } else if (d.type === 'po') {
    rows.push(`Value: $${Number(d.value || 0).toLocaleString()}`, `Status: ${d.status}`);
    if (d.has_deviation) {
      rows.push(`<span style="color:#dc5643;">⚠ Deviation: ${d.deviation_severity}</span>`);
    }
  } else if (d.type === 'customer_order') {
    rows.push(`Value: $${Number(d.value || 0).toLocaleString()}`, `Status: ${d.status}`);
  } else if (d.type === 'customer') {
    rows.push(`Segment: ${d.segment}`);
  }
  return rows.join('<br>');
}

async function buildGraph(limit) {
  const container = document.getElementById('graph-canvas');
  container.innerHTML = '';

  let data;
  try {
    data = await fetch(`/api/graph?limit=${limit}`).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
  } catch (err) {
    container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;
        height:100%;color:var(--critical);font-size:13px;">
      Failed to load graph: ${err.message}</div>`;
    return;
  }

  document.getElementById('graph-stats').textContent =
    `${data.node_count} nodes · ${data.edge_count} edges`;

  if (!data.node_count) {
    container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;
        height:100%;color:var(--text-muted);font-size:13px;">
      No graph data available.</div>`;
    return;
  }

  const W = container.clientWidth || 900;
  const H = 600;

  _zoomBehaviour = d3.zoom().scaleExtent([0.15, 5])
    .on('zoom', e => g.attr('transform', e.transform));

  const svg = d3.select('#graph-canvas').append('svg')
    .attr('width', W).attr('height', H)
    .call(_zoomBehaviour);

  _svg = svg;

  // Arrow marker
  svg.append('defs').append('marker')
    .attr('id', 'dt-arrow')
    .attr('viewBox', '0 -4 8 8')
    .attr('refX', 16).attr('refY', 0)
    .attr('markerWidth', 5).attr('markerHeight', 5)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-4L8,0L0,4')
    .attr('fill', '#c3d0b6');

  const g = svg.append('g');

  const links = g.append('g').selectAll('line')
    .data(data.edges).enter().append('line')
    .attr('stroke', '#dfe7d6')
    .attr('stroke-width', 0.8)
    .attr('marker-end', 'url(#dt-arrow)');

  const tooltip = document.getElementById('graph-tooltip');

  const nodes = g.append('g').selectAll('circle')
    .data(data.nodes).enter().append('circle')
    .attr('r', nodeRadius)
    .attr('fill', nodeColor)
    .attr('stroke', d => d.has_deviation ? '#dc5643' : 'rgba(28,42,29,0.15)')
    .attr('stroke-width', d => d.has_deviation ? 2 : 0.5)
    .style('cursor', 'pointer')
    .call(
      d3.drag()
        .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    )
    .on('mouseover', (e, d) => {
      tooltip.innerHTML = tooltipHtml(d);
      tooltip.style.display = 'block';
      tooltip.style.left = (e.pageX + 14) + 'px';
      tooltip.style.top = (e.pageY - 10) + 'px';
    })
    .on('mousemove', e => {
      tooltip.style.left = (e.pageX + 14) + 'px';
      tooltip.style.top = (e.pageY - 10) + 'px';
    })
    .on('mouseout', () => { tooltip.style.display = 'none'; });

  // Labels only for supplier and customer nodes — too many POs to label
  const labels = g.append('g').selectAll('text')
    .data(data.nodes.filter(n => n.type === 'customer' || n.type === 'supplier'))
    .enter().append('text')
    .text(d => d.label.length > 22 ? d.label.slice(0, 20) + '…' : d.label)
    .attr('font-size', 8)
    .attr('font-family', 'IBM Plex Mono, monospace')
    .attr('fill', '#56634f')
    .attr('dy', d => nodeRadius(d) + 10)
    .attr('text-anchor', 'middle')
    .style('pointer-events', 'none')
    .style('user-select', 'none');

  const sim = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges).id(d => d.id).distance(50).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-90))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(d => nodeRadius(d) + 5))
    .on('tick', () => {
      links
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      nodes.attr('cx', d => d.x).attr('cy', d => d.y);
      labels.attr('x', d => d.x).attr('y', d => d.y);
    });
}

function resetZoom() {
  if (_svg && _zoomBehaviour) {
    _svg.transition().duration(450)
      .call(_zoomBehaviour.transform, d3.zoomIdentity);
  }
}

function reloadGraph() {
  const limit = parseInt(document.getElementById('limit-select').value, 10);
  buildGraph(limit);
}

buildGraph(80);
