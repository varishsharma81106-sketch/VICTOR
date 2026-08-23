/* Victor console.
   Vanilla JS, no build step, no CDN — Victor is offline-first and the
   interface has to hold that line too. The force layout below is deliberately
   small rather than pulling in d3. */

'use strict';

const TYPE_COLORS = {
  paper: '#4da3ff', claim: '#f0b429', concept: '#48c78e', experiment: '#ff8f4d',
  observation: '#00c2d1', conversation: '#8b98a8', note: '#c9a6ff', computed: '#ff6ec7',
};
const MASKED_COLOR = '#b07cf0';
const colorFor = t => TYPE_COLORS[t] || '#6b7684';

const $  = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).error || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}
const get  = p       => api(p);
const post = (p, b)  => api(p, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}),
});

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove('show'), 2600);
}

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function ago(iso) {
  if (!iso) return '—';
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (isNaN(d)) return '—';
  if (d < 60) return 'just now';
  if (d < 3600) return Math.floor(d / 60) + 'm ago';
  if (d < 86400) return Math.floor(d / 3600) + 'h ago';
  return Math.floor(d / 86400) + 'd ago';
}

/* ── tabs ─────────────────────────────────────────────────────────────── */

const LOADERS = {};
let currentView = 'overview';

$$('.tab').forEach(tab => tab.addEventListener('click', () => {
  $$('.tab').forEach(t => t.classList.remove('active'));
  $$('.view').forEach(v => v.classList.remove('active'));
  tab.classList.add('active');
  currentView = tab.dataset.view;
  $('#view-' + currentView).classList.add('active');
  if (LOADERS[currentView]) LOADERS[currentView]();
}));

/* ── overview ─────────────────────────────────────────────────────────── */

function barRow(label, n, max, color) {
  const pct = max ? (n / max) * 100 : 0;
  return `<div class="bar-row">
    <span class="lbl">${esc(label)}</span>
    <span class="track"><span class="fill" style="width:${pct}%;background:${color}"></span></span>
    <span class="n">${n}</span>
  </div>`;
}

LOADERS.overview = async () => {
  let o, act;
  try {
    [o, act] = await Promise.all([get('/api/overview'), get('/api/activity?limit=25')]);
  } catch (e) { $('#stat-grid').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  const llm = $('#llm-status');
  llm.className = 'llm ' + (o.llm.online ? 'online' : 'offline');
  $('#llm-text').textContent = o.llm.online
    ? `${o.llm.model} · ${o.llm.retriever}`
    : `${o.llm.model} offline`;

  $('#stat-grid').innerHTML = [
    { k: 'Nodes',       v: o.nodes,   cls: 'accent' },
    { k: 'Connections', v: o.edges,   note: `${o.density} per node` },
    { k: 'Masked',      v: o.masked,  cls: 'masked', note: 'content withheld' },
    { k: 'Frozen',      v: o.frozen,  note: 'immutable' },
    { k: 'Retrievals',  v: o.total_retrievals, cls: 'good', note: 'times consulted' },
    { k: 'Mean weight', v: o.mean_importance,  note: 'importance' },
  ].map(s => `<div class="stat ${s.cls || ''}">
      <div class="v">${s.v}</div><div class="k">${s.k}</div>
      ${s.note ? `<div class="note">${s.note}</div>` : ''}
    </div>`).join('');

  const types = Object.entries(o.by_type).sort((a, b) => b[1] - a[1]);
  const tmax = Math.max(1, ...types.map(t => t[1]));
  $('#by-type').innerHTML = types.length
    ? types.map(([t, n]) => barRow(t, n, tmax, colorFor(t))).join('')
    : '<div class="empty">Nothing ingested yet.</div>';

  const ORDER = ['measurement', 'experiment', 'literature', 'note', 'hypothesis'];
  const st = Object.entries(o.by_epistemic_status)
    .sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]));
  const smax = Math.max(1, ...st.map(s => s[1]));
  const SC = { measurement: '#48c78e', experiment: '#4da3ff', literature: '#f0b429', note: '#8b98a8', hypothesis: '#f2555a' };
  $('#by-status').innerHTML = st.length
    ? st.map(([s, n]) => barRow(s, n, smax, SC[s] || '#6b7684')).join('')
    : '<div class="empty">No epistemic tags yet.</div>';

  $('#activity').innerHTML = act.activity.length
    ? act.activity.map(a => `<div class="item ${a.masked ? 'is-masked' : ''}">
        <span class="pill ${esc(a.ntype)}">${esc(a.ntype)}</span>
        <div class="grow">
          <div class="title ${a.masked ? 'redacted' : ''}">${esc(a.label)}</div>
          <div class="meta"><span>${ago(a.at)}</span><span>retrieved ${a.retrieval_count}×</span></div>
        </div></div>`).join('')
    : '<div class="empty">No activity yet.</div>';
};

/* ── graph ────────────────────────────────────────────────────────────── */

const G = {
  nodes: [], links: [], byId: new Map(),
  cam: { x: 0, y: 0, z: 1 },
  drag: null, selected: null, hover: null,
  raf: null, alpha: 1, loaded: false,
};

LOADERS.graph = async () => {
  if (G.loaded) { sizeCanvas(); return; }
  const data = await get('/api/graph');
  G.loaded = true;

  // Seed on a circle rather than at random: a deterministic start means the
  // layout settles the same way every reload, so the picture you learn is stable.
  const N = data.nodes.length || 1;
  G.nodes = data.nodes.map((n, i) => {
    const a = (i / N) * Math.PI * 2;
    return Object.assign({}, n, {
      x: Math.cos(a) * 240, y: Math.sin(a) * 240, vx: 0, vy: 0,
      deg: 0, r: 5,
    });
  });
  G.byId = new Map(G.nodes.map(n => [n.id, n]));
  G.links = data.links
    .map(l => ({ s: G.byId.get(l.source), t: G.byId.get(l.target), etype: l.etype }))
    .filter(l => l.s && l.t);
  G.links.forEach(l => { l.s.deg++; l.t.deg++; });
  G.nodes.forEach(n => { n.r = 4 + Math.sqrt(n.deg) * 2.1 + n.importance * 2.4; });

  const types = [...new Set(G.nodes.map(n => n.ntype))].sort();
  $('#legend-types').innerHTML = types.map(t =>
    `<div class="legend-row"><span class="swatch" style="background:${colorFor(t)}"></span> ${esc(t)}</div>`
  ).join('');

  if (data.truncated) {
    toast(`Showing the ${data.nodes.length} most important of ${data.total_nodes} nodes`);
  }

  G.alpha = 1;
  sizeCanvas();
  tick();
};

const canvas = $('#graph-canvas');
const ctx = canvas.getContext('2d');

function sizeCanvas() {
  const r = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = r.width * dpr;
  canvas.height = r.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}
window.addEventListener('resize', () => { if (currentView === 'graph') sizeCanvas(); });

/* One step of a Fruchterman-Reingold-ish layout. Repulsion is O(n²), which is
   fine at the few-hundred-node scale the API caps at and keeps this readable. */
function step() {
  const REPEL = 5200, SPRING = 0.012, LEN = 62, CENTER = 0.0016, DAMP = 0.86;
  const n = G.nodes;
  for (let i = 0; i < n.length; i++) {
    const a = n[i];
    for (let j = i + 1; j < n.length; j++) {
      const b = n[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 0.01) { dx = (Math.random() - 0.5) * 0.1; dy = (Math.random() - 0.5) * 0.1; d2 = 0.01; }
      const f = REPEL / d2;
      const d = Math.sqrt(d2);
      const fx = (dx / d) * f, fy = (dy / d) * f;
      a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
    }
  }
  for (const l of G.links) {
    const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y;
    const d = Math.hypot(dx, dy) || 0.01;
    const f = (d - LEN) * SPRING;
    const fx = (dx / d) * f, fy = (dy / d) * f;
    l.s.vx += fx; l.s.vy += fy; l.t.vx -= fx; l.t.vy -= fy;
  }
  for (const a of n) {
    a.vx -= a.x * CENTER; a.vy -= a.y * CENTER;
    if (a === G.drag) { a.vx = a.vy = 0; continue; }
    a.vx *= DAMP; a.vy *= DAMP;
    a.x += a.vx * G.alpha; a.y += a.vy * G.alpha;
  }
}

function tick() {
  if (G.alpha > 0.008) { step(); G.alpha *= 0.994; }
  draw();
  G.raf = requestAnimationFrame(tick);
}

function draw() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  ctx.clearRect(0, 0, w, h);
  ctx.save();
  ctx.translate(w / 2 + G.cam.x, h / 2 + G.cam.y);
  ctx.scale(G.cam.z, G.cam.z);

  // edges
  ctx.lineWidth = 1 / G.cam.z;
  for (const l of G.links) {
    const hot = G.selected && (l.s.id === G.selected || l.t.id === G.selected);
    ctx.strokeStyle = hot ? 'rgba(77,163,255,.55)' : 'rgba(255,255,255,.055)';
    ctx.beginPath();
    ctx.moveTo(l.s.x, l.s.y);
    ctx.lineTo(l.t.x, l.t.y);
    ctx.stroke();
  }

  // nodes
  for (const n of G.nodes) {
    const sel = n.id === G.selected, hov = n.id === G.hover;
    const shown = n.masked && !n.revealed;

    if (shown) {
      // A masked node is drawn as a hollow dashed ring: present, placed, sized
      // by its real degree and importance — but visibly hollow. The picture and
      // the mechanism say the same thing.
      ctx.setLineDash([2.5 / G.cam.z, 2.5 / G.cam.z]);
      ctx.strokeStyle = MASKED_COLOR;
      ctx.lineWidth = 1.6 / G.cam.z;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(176,124,240,.13)';
      ctx.fill();
    } else {
      ctx.fillStyle = colorFor(n.ntype);
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
      if (n.revealed) {
        ctx.strokeStyle = MASKED_COLOR;
        ctx.lineWidth = 1.6 / G.cam.z;
        ctx.stroke();
      }
    }

    if (n.frozen) {
      ctx.strokeStyle = '#4da3ff';
      ctx.lineWidth = 1.2 / G.cam.z;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 2.5 / G.cam.z, 0, Math.PI * 2); ctx.stroke();
    }
    if (sel || hov) {
      ctx.strokeStyle = sel ? '#fff' : 'rgba(255,255,255,.5)';
      ctx.lineWidth = 1.6 / G.cam.z;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 4 / G.cam.z, 0, Math.PI * 2); ctx.stroke();
    }

    // Labels only when zoomed in enough to read them, or on focus.
    if (G.cam.z > 0.82 || sel || hov) {
      const t = shown ? '████' : (n.label || '').slice(0, 34);
      ctx.fillStyle = shown ? MASKED_COLOR : 'rgba(219,226,234,.82)';
      ctx.font = `${11 / G.cam.z}px ui-monospace, monospace`;
      ctx.textAlign = 'center';
      ctx.fillText(t, n.x, n.y + n.r + 11 / G.cam.z);
    }
  }
  ctx.restore();
}

function toWorld(ev) {
  const r = canvas.getBoundingClientRect();
  return {
    x: (ev.clientX - r.left - r.width / 2 - G.cam.x) / G.cam.z,
    y: (ev.clientY - r.top - r.height / 2 - G.cam.y) / G.cam.z,
  };
}
function nodeAt(p) {
  for (let i = G.nodes.length - 1; i >= 0; i--) {
    const n = G.nodes[i];
    if (Math.hypot(n.x - p.x, n.y - p.y) <= n.r + 4) return n;
  }
  return null;
}

let panning = null;
canvas.addEventListener('mousedown', ev => {
  const hit = nodeAt(toWorld(ev));
  if (hit) { G.drag = hit; G.alpha = Math.max(G.alpha, 0.35); }
  else { panning = { x: ev.clientX - G.cam.x, y: ev.clientY - G.cam.y }; canvas.classList.add('dragging'); }
});
canvas.addEventListener('mousemove', ev => {
  if (G.drag) { const p = toWorld(ev); G.drag.x = p.x; G.drag.y = p.y; return; }
  if (panning) { G.cam.x = ev.clientX - panning.x; G.cam.y = ev.clientY - panning.y; draw(); return; }
  const hit = nodeAt(toWorld(ev));
  const id = hit ? hit.id : null;
  if (id !== G.hover) { G.hover = id; canvas.style.cursor = hit ? 'pointer' : 'grab'; draw(); }
});
window.addEventListener('mouseup', ev => {
  if (G.drag) {
    // A click is a press that didn't move: only treat it as selection.
    const p = toWorld(ev);
    if (Math.hypot(G.drag.x - p.x, G.drag.y - p.y) < 6) selectNode(G.drag.id);
    G.drag = null;
  }
  panning = null;
  canvas.classList.remove('dragging');
});
canvas.addEventListener('wheel', ev => {
  ev.preventDefault();
  const f = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
  G.cam.z = Math.min(4, Math.max(0.18, G.cam.z * f));
  draw();
}, { passive: false });

async function selectNode(id) {
  G.selected = id;
  draw();
  const box = $('#inspector');
  box.innerHTML = '<div class="spinner">Loading…</div>';
  let n;
  try { n = await get('/api/node/' + encodeURIComponent(id)); }
  catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  const hidden = n.masked && !n.revealed;
  const edges = (list, dir) => list.length ? `
    <div class="eh">${dir} (${list.length})</div>
    ${list.map(e => `<div class="edge" data-goto="${esc(e.id)}">
        <span class="et">${esc(e.etype || 'related')}</span>
        <span class="${e.masked ? 'redacted' : ''}">${esc((e.label || '').slice(0, 46))}</span>
      </div>`).join('')}` : '';

  box.innerHTML = `
    <h3 class="${hidden ? 'redacted' : ''}">${esc(hidden ? '████████' : n.label)}</h3>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin:7px 0">
      <span class="pill ${esc(n.ntype)}">${esc(n.ntype)}</span>
      ${n.masked ? `<span class="pill masked">${n.revealed ? 'revealed' : 'masked'}</span>` : ''}
      ${n.frozen ? '<span class="pill">frozen</span>' : ''}
      ${n.epistemic_status ? `<span class="pill">${esc(n.epistemic_status)}</span>` : ''}
    </div>
    <dl class="kv">
      <dt>id</dt><dd>${esc(n.id.slice(0, 20))}</dd>
      <dt>importance</dt><dd>${n.importance}</dd>
      <dt>retrieved</dt><dd>${n.retrieval_count}× · ${ago(n.last_retrieved_at)}</dd>
      <dt>degree</dt><dd>${n.degree_in} in / ${n.degree_out} out</dd>
    </dl>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
      ${n.masked
        ? (n.revealed
            ? `<button class="act" data-conceal="${esc(n.id)}">Hide again</button>`
            : `<button class="act" data-reveal="${esc(n.id)}">Reveal for this session</button>`)
          + `<button class="act danger" data-unmask="${esc(n.id)}">Unmask permanently</button>`
        : `<button class="act" data-mask="${esc(n.id)}">Mask this node</button>`}
    </div>
    <div class="edge-list">${edges(n.in_edges, 'incoming')}${edges(n.out_edges, 'outgoing')}</div>`;
}

/* Delegated so buttons rendered into the inspector and the vault share one path. */
document.addEventListener('click', async ev => {
  const el = ev.target.closest('[data-goto],[data-reveal],[data-conceal],[data-mask],[data-unmask]');
  if (!el) return;
  const d = el.dataset;
  try {
    if (d.goto)    { selectNode(d.goto); return; }
    if (d.reveal)  { await post('/api/reveal',  { node_id: d.reveal });  toast('Revealed for this session'); }
    if (d.conceal) { await post('/api/conceal', { node_id: d.conceal }); toast('Hidden again'); }
    if (d.mask)    { await post('/api/mask',    { node_id: d.mask });    toast('Node masked'); }
    if (d.unmask)  { await post('/api/unmask',  { node_id: d.unmask });  toast('Node unmasked permanently'); }
  } catch (e) { toast('Failed: ' + e.message); return; }

  const id = d.reveal || d.conceal || d.mask || d.unmask;
  // Mask state changed, so the cached graph is stale in exactly one node.
  const gn = G.byId.get(id);
  if (gn) {
    if (d.reveal)  gn.revealed = true;
    if (d.conceal) gn.revealed = false;
    if (d.mask)   { gn.masked = true;  gn.revealed = false; }
    if (d.unmask) { gn.masked = false; gn.revealed = false; }
    draw();
  }
  if (G.selected === id) selectNode(id);
  if (currentView === 'vault') LOADERS.vault();
});

/* ── ask ──────────────────────────────────────────────────────────────── */

async function runAsk() {
  const q = $('#ask-input').value.trim();
  if (!q) return;
  const btn = $('#ask-btn'), out = $('#ask-result');
  btn.disabled = true;
  out.innerHTML = '<div class="panel"><div class="spinner">Retrieving, reviewing, reasoning…</div></div>';

  let r;
  try { r = await post('/api/ask', { query: q }); }
  catch (e) { out.innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; btn.disabled = false; return; }
  btn.disabled = false;

  const maskedCount = r.chunks.filter(c => c.masked_anchor).length;
  out.innerHTML = `
    ${r.no_context ? '<div class="notice warn">Victor found no relevant context. This answer is not grounded in its memory.</div>' : ''}
    ${maskedCount ? `<div class="notice">${maskedCount} of ${r.chunks.length} retrieved sources are masked.
       Victor used their position in the graph but could not read them.</div>` : ''}
    <div class="panel"><h2>Answer</h2><div class="answer">${esc(r.answer)}</div></div>
    <div class="panel">
      <h2>Provenance — ${r.chunks.length} source${r.chunks.length === 1 ? '' : 's'}</h2>
      <p class="hint">${esc(r.provenance_summary || '')} · answered by ${esc(r.provider)}</p>
      ${r.chunks.map(c => `<div class="chunk ${c.masked_anchor ? 'masked-anchor' : ''}">
        <div class="ch-head">
          <span class="pill ${esc(c.masked_anchor ? 'masked' : c.source_type)}">${esc(c.epistemic_status)}</span>
          <span class="mono" style="font-size:11px;color:var(--text-dim)">${esc(c.source_title)}</span>
          <span class="mono" style="font-size:10.5px;color:var(--text-faint)">score ${c.score}</span>
        </div>
        <div class="ch-text">${esc(c.text.slice(0, 420))}${c.text.length > 420 ? '…' : ''}</div>
        ${c.provenance.length ? `<div class="ch-prov">${esc(c.provenance.join(' · '))}</div>` : ''}
      </div>`).join('') || '<div class="empty">No sources retrieved.</div>'}
    </div>`;
}
$('#ask-btn').addEventListener('click', runAsk);
$('#ask-input').addEventListener('keydown', e => { if (e.key === 'Enter') runAsk(); });

/* ── gaps ─────────────────────────────────────────────────────────────── */

LOADERS.gaps = async () => {
  const t = parseFloat($('#gap-threshold').value);
  $('#gap-threshold-val').textContent = t.toFixed(2);
  const box = $('#gaps-list');
  box.innerHTML = '<div class="spinner">Loading…</div>';
  let r;
  try { r = await get('/api/gaps?min_importance=' + t); }
  catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  box.innerHTML = r.gaps.length ? r.gaps.map(g => `
    <div class="item ${g.masked ? 'is-masked' : ''}">
      <span class="pill ${esc(g.epistemic_status)}">${esc(g.epistemic_status)}</span>
      <div class="grow">
        <div class="title ${g.masked ? 'redacted' : ''}">${esc(g.claim_text)}</div>
        <div class="meta">
          <span>importance ${g.importance}</span>
          <span>confidence ${g.confidence}</span>
          <span>${g.n_confirms} confirm · ${g.n_contradicts} contradict · ${g.n_inconclusive} unclear</span>
        </div>
      </div>
      <button class="act" data-goto="${esc(g.claim_id)}">Inspect</button>
    </div>`).join('')
    : '<div class="empty">No unverified claims above this threshold.</div>';
};
$('#gap-threshold').addEventListener('input', () => {
  $('#gap-threshold-val').textContent = parseFloat($('#gap-threshold').value).toFixed(2);
});
$('#gap-threshold').addEventListener('change', LOADERS.gaps);

/* ── vault ────────────────────────────────────────────────────────────── */

LOADERS.vault = async () => {
  const box = $('#vault-list');
  let r;
  try { r = await get('/api/masked'); }
  catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  box.innerHTML = r.count ? r.masked.map(m => `
    <div class="item is-masked">
      <span class="pill ${esc(m.ntype)}">${esc(m.ntype)}</span>
      <div class="grow">
        <div class="title ${m.revealed ? '' : 'redacted'}">${esc(m.label)}</div>
        <div class="meta">
          <span class="mono">${esc(m.id.slice(0, 16))}</span>
          <span>${m.degree} relation${m.degree === 1 ? '' : 's'} live</span>
          <span>importance ${m.importance}</span>
          <span>retrieved ${m.retrieval_count}×</span>
        </div>
      </div>
      ${m.revealed
        ? `<button class="act" data-conceal="${esc(m.id)}">Hide</button>`
        : `<button class="act" data-reveal="${esc(m.id)}">Reveal</button>`}
      <button class="act danger" data-unmask="${esc(m.id)}">Unmask</button>
    </div>`).join('')
    : '<div class="empty">Nothing is masked. Mask a node from the graph view to withhold its content.</div>';
};

/* ── audit ────────────────────────────────────────────────────────────── */

LOADERS.audit = async () => {
  const box = $('#audit-list');
  let r;
  try { r = await get('/api/audit'); }
  catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  const cls = a => a.startsWith('unmask') || a === 'session-reveal' ? 'bad' : 'good';
  box.innerHTML = r.entries.length ? r.entries.map(e => `
    <div class="item">
      <span class="pill ${cls(e.action || '')}">${esc(e.action)}</span>
      <div class="grow">
        <div class="title mono" style="font-size:12px">${esc(e.node_id || '')}</div>
        <div class="meta">
          <span>${esc(e.ts || '')}</span>
          <span>${ago(e.ts)}</span>
          <span>${e.success ? 'ok' : 'failed'}</span>
          ${e.caller ? `<span>${esc(e.caller)}</span>` : ''}
        </div>
      </div>
    </div>`).join('')
    : '<div class="empty">No mask activity recorded yet.</div>';
};

/* ── boot ─────────────────────────────────────────────────────────────── */

LOADERS.overview();
