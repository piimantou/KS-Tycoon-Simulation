"""Shared single-page UI markup + logic.

Both front-ends render the exact same page; they differ only in the *data
layer*. ``PAGE`` carries two placeholders:

  ``__HEAD_EXTRA__``  extra <head> content (e.g. the Pyodide <script> tag)
  ``__API__``         a JS block defining ``const api = {...}`` with:
                        api.newState()              -> state object
                        api.tick(state, decisions)  -> {report, state, result} | {error}
                        api.reset()                 -> fresh state object
                        api.persist(state)          (optional) save hook

This keeps the markup, CSS and render logic in one place (no drift between the
local server and the in-browser build).
"""

from __future__ import annotations

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KS-Tycoon — Umpire Console</title>
__HEAD_EXTRA__
<style>
  :root { --bg:#10141a; --panel:#1a2029; --line:#2c3542; --ink:#e6edf3;
          --mut:#8b97a6; --accent:#5aa9e6; --good:#5fd38a; --warn:#e6b35a; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--ink); }
  header { padding:14px 20px; border-bottom:1px solid var(--line);
           display:flex; gap:24px; align-items:baseline; flex-wrap:wrap; }
  header h1 { font-size:16px; margin:0; letter-spacing:.5px; }
  header .stat { color:var(--mut); } header .stat b { color:var(--ink); }
  #boot { padding:6px 20px; background:#202a36; color:var(--mut); font-size:13px;
          border-bottom:1px solid var(--line); }
  #boot.err { color:#ff9b9b; }
  .wrap { display:grid; grid-template-columns: 360px 1fr; gap:16px; padding:16px; }
  @media (max-width:880px){ .wrap{ grid-template-columns:1fr; } }
  .panel { background:var(--panel); border:1px solid var(--line);
           border-radius:8px; padding:14px; margin-bottom:16px; }
  .panel h2 { font-size:13px; text-transform:uppercase; letter-spacing:.6px;
              color:var(--mut); margin:0 0 10px; }
  label { display:block; font-size:12px; color:var(--mut); margin:8px 0 2px; }
  input, select { width:100%; padding:6px 8px; background:#0d1117;
                  border:1px solid var(--line); border-radius:5px; color:var(--ink); }
  .row { display:flex; gap:8px; } .row > * { flex:1; }
  button { cursor:pointer; border:1px solid var(--line); background:#222b36;
           color:var(--ink); padding:8px 12px; border-radius:6px; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#06121f;
                   font-weight:600; width:100%; padding:10px; margin-top:12px; }
  button:disabled { opacity:.5; cursor:wait; }
  button.mini { padding:3px 8px; font-size:12px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:5px 6px; border-bottom:1px solid var(--line); }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  .chk { display:flex; align-items:center; gap:8px; margin:4px 0; }
  .chk input { width:auto; }
  .ord { display:flex; gap:6px; align-items:center; margin:4px 0; font-size:13px; }
  .ord .rm { color:var(--warn); }
  pre { white-space:pre-wrap; background:#0d1117; border:1px solid var(--line);
        border-radius:6px; padding:12px; font-size:12px; color:#cdd6e0; }
  .warn { color:var(--warn); } .muted { color:var(--mut); }
</style>
</head>
<body>
<header>
  <h1>KS-TYCOON · UMPIRE CONSOLE</h1>
  <span class="stat">Nation <b id="h-nation">—</b></span>
  <span class="stat">FY <b id="h-year">—</b></span>
  <span class="stat">Pop <b id="h-pop">—</b></span>
  <span class="stat">GDP/cap <b id="h-gdp">—</b></span>
  <span class="stat">Stability <b id="h-stab">—</b></span>
  <span class="stat">Treasury <b id="h-treasury">—</b></span>
  <span class="stat">Debt <b id="h-debt">—</b></span>
  <span class="stat" style="margin-left:auto"><button class="mini" id="reset">Reset to Y0</button></span>
</header>
<div id="boot">Starting…</div>

<div class="wrap">
  <div>
    <div class="panel">
      <h2>Fiscal &amp; mobilisation</h2>
      <label>Income tax rate (<span id="lbl-tax"></span>)</label>
      <input id="tax" type="range" min="0" max="0.6" step="0.01">
      <div class="row">
        <div><label>Civilian share</label><input id="civ" type="number" min="0" max="1" step="0.01"></div>
        <div><label>Defense share</label><input id="def" type="number" min="0" max="1" step="0.01"></div>
      </div>
      <label>Mobilisation readiness</label>
      <select id="readiness">
        <option value="1">I — Routine (volunteers)</option>
        <option value="2">II — Alert</option>
        <option value="3">III — Partial (Conscription I)</option>
        <option value="4">IV — General (Conscription II)</option>
      </select>
    </div>
    <div class="panel"><h2>Development projects</h2><div id="projects" class="muted">—</div></div>
    <div class="panel">
      <h2>Procurement orders</h2>
      <div class="row">
        <select id="ord-unit"></select>
        <select id="ord-chan"><option value="domestic">Domestic</option><option value="import">Import</option></select>
      </div>
      <div class="row" style="margin-top:6px">
        <input id="ord-qty" type="number" min="1" value="1" placeholder="qty">
        <button class="mini" id="ord-add">Add order</button>
      </div>
      <div id="orders" style="margin-top:8px"></div>
    </div>
    <button class="primary" id="run" disabled>▶ Run Financial Year</button>
  </div>

  <div>
    <div class="panel"><h2>Public finance</h2>
      <div id="finance" class="muted">Run a year to compute revenue &amp; budgets.</div></div>
    <div class="panel"><h2>Population</h2>
      <table><thead><tr><th>Stratum</th><th class="num">Size</th>
        <th class="num">Income/cap</th><th class="num">SoL</th><th class="num">Loyalty</th>
        <th class="num">Wealth</th></tr></thead>
        <tbody id="pops"></tbody></table></div>
    <div class="panel"><h2>Market</h2>
      <table><thead><tr><th>Good</th><th class="num">Price</th><th class="num">Base</th></tr></thead>
        <tbody id="goods"></tbody></table></div>
    <div class="panel"><h2>Force handoff → tactical layer</h2>
      <table><thead><tr><th>Token</th><th class="num">Operational</th>
        <th class="num">Training</th><th class="num">Men/tok</th></tr></thead>
        <tbody id="forces"><tr><td class="muted" colspan="4">Run a year.</td></tr></tbody></table></div>
    <div class="panel"><h2>Handoff report</h2>
      <div id="warnings"></div><pre id="report" class="muted">—</pre></div>
  </div>
</div>

<script>
// Helpers first: the API block below may run an immediate bootstrap that
// calls boot()/$, so these must be initialised before it (avoids a
// temporal-dead-zone "Cannot access $ before initialization").
let STATE = null;
const orders = [];
const $ = (id) => document.getElementById(id);
const fmt = (n) => (n==null?'—':Number(n).toLocaleString(undefined,{maximumFractionDigits:0}));
function boot(msg, err){ const b=$('boot'); b.textContent=msg; b.className=err?'err':''; }

__API__

async function start(){
  try {
    STATE = await api.newState();
    $('run').disabled = false;
    boot('Ready — engine running in your browser. Set this year\'s directives and Run.');
    render();
  } catch (e) { boot('Failed to start engine: ' + e, true); }
}

function render(){
  const s = STATE, g = s.government, mp = s.manpower;
  $('h-nation').textContent = s.nation;
  $('h-year').textContent = s.year;
  $('h-pop').textContent = fmt(mp.population);
  $('h-gdp').textContent = '$' + fmt(s.gdp / mp.population);
  $('h-stab').textContent = (s.stability).toFixed(2);
  $('h-treasury').textContent = '$' + fmt(g.treasury);
  $('h-debt').textContent = '$' + fmt(g.debt);
  $('tax').value = g.income_tax_rate; $('lbl-tax').textContent = (g.income_tax_rate*100).toFixed(0)+'%';
  $('civ').value = g.civilian_share; $('def').value = g.defense_share;
  $('readiness').value = mp.readiness;

  const pj = $('projects'); pj.innerHTML = '';
  Object.values(s.projects).forEach(p => {
    const done = p.remaining_years <= 0;
    const div = document.createElement('div'); div.className = 'chk';
    div.innerHTML = `<input type="checkbox" id="pj-${p.id}" ${done?'disabled':''}>
      <span>${p.name} <span class="muted">($${fmt(p.allocation)}, ${done?'complete':p.remaining_years+'y left'})</span></span>`;
    pj.appendChild(div);
  });

  const sel = $('ord-unit'); sel.innerHTML = '';
  Object.values(s.units).forEach(u => {
    const o = document.createElement('option'); o.value = u.id;
    o.textContent = u.name + ` (${u.category})`; sel.appendChild(o);
  });

  $('pops').innerHTML = Object.values(s.pops).map(p => {
    const pc = p.size ? p.income/p.size : 0;
    return `<tr><td>${p.name}</td><td class="num">${fmt(p.size)}</td>
      <td class="num">$${fmt(pc)}</td><td class="num">${(p.sol).toFixed(2)}</td>
      <td class="num">${(p.loyalty).toFixed(2)}</td><td class="num">$${fmt(p.wealth)}</td></tr>`;
  }).join('');
  $('goods').innerHTML = Object.values(s.goods).map(gd =>
    `<tr><td>${gd.name}</td><td class="num">${gd.price.toFixed(2)}</td>
      <td class="num">${gd.base_price.toFixed(2)}</td></tr>`).join('');
  renderOrders();
}

function renderOrders(){
  $('orders').innerHTML = orders.map((o,i) => {
    const u = STATE.units[o.unit_token_id];
    return `<div class="ord"><span>${u?u.name:o.unit_token_id} · ${o.channel} · ${o.quantity}</span>
      <a class="rm" href="#" onclick="rmOrder(${i});return false">remove</a></div>`;
  }).join('') || '<span class="muted">No orders queued.</span>';
}
window.rmOrder = (i) => { orders.splice(i,1); renderOrders(); };

$('tax').addEventListener('input', e => $('lbl-tax').textContent = (e.target.value*100).toFixed(0)+'%');
$('ord-add').addEventListener('click', () => {
  const q = parseInt($('ord-qty').value||'0',10);
  if (q>0){ orders.push({unit_token_id:$('ord-unit').value, channel:$('ord-chan').value, quantity:q}); renderOrders(); }
});
$('reset').addEventListener('click', async () => {
  STATE = await api.reset(); orders.length=0;
  $('report').textContent='—'; $('warnings').innerHTML='';
  $('forces').innerHTML='<tr><td class="muted" colspan="4">Run a year.</td></tr>';
  $('finance').innerHTML='<span class="muted">Run a year to compute revenue &amp; budgets.</span>';
  render();
});

$('run').addEventListener('click', async () => {
  const btn = $('run'); btn.disabled = true; btn.textContent = '… resolving';
  try {
    const projIds = Object.values(STATE.projects)
      .filter(p => { const el = $('pj-'+p.id); return el && el.checked; }).map(p => p.id);
    const decisions = {
      income_tax_rate: parseFloat($('tax').value),
      civilian_share: parseFloat($('civ').value),
      defense_share: parseFloat($('def').value),
      readiness: parseInt($('readiness').value,10),
      new_project_ids: projIds,
      procurement_orders: orders.slice(),
    };
    const data = await api.tick(STATE, decisions);
    if (data.error){ $('warnings').innerHTML = `<div class="warn">Error: ${data.error}</div>`; return; }
    STATE = data.state; orders.length = 0; if (api.persist) api.persist(STATE); render();

    const g = STATE.government, r = data.result;
    $('finance').innerHTML = `<table>
      <tr><td>Tax revenue (${(g.income_tax_rate*100).toFixed(0)}%)</td><td class="num">$${fmt(g.revenue)}</td></tr>
      <tr><td>Civilian budget</td><td class="num">$${fmt(g.civilian_budget)}</td></tr>
      <tr><td>Defense budget</td><td class="num">$${fmt(g.defense_budget)}</td></tr>
      <tr><td>Procurement spend</td><td class="num">$${fmt(r.procurement_cost)}</td></tr>
      <tr><td>Personnel (wages)</td><td class="num">$${fmt(r.personnel_cost)}</td></tr>
      <tr><td>Project spend</td><td class="num">$${fmt(r.project_cost)}</td></tr>
      <tr><td>Forex reserve</td><td class="num">$${fmt(g.forex_reserve)}</td></tr></table>`;

    const op = r.operational_tokens, tr = r.training_tokens;
    const keys = new Set([...Object.keys(op), ...Object.keys(tr)]);
    $('forces').innerHTML = [...keys].map(k => {
      const u = STATE.units[k];
      return `<tr><td>${u?u.name:k}</td><td class="num">${op[k]||0}</td>
        <td class="num">${tr[k]||0}</td><td class="num">${u?u.men_per_token:'?'}</td></tr>`;
    }).join('') || '<tr><td class="muted" colspan="4">No forces.</td></tr>';

    const warns = r.warnings || [];
    $('warnings').innerHTML = warns.length
      ? '<div class="warn">' + warns.map(w => '⚠ '+w).join('<br>') + '</div>' : '';
    $('report').textContent = data.report;
  } finally { btn.disabled = false; btn.textContent = '▶ Run Financial Year'; }
});

start();
</script>
</body>
</html>
"""
