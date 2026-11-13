"""Static site: every game's ledger in one self-contained page, browsable tick by tick."""
from __future__ import annotations

import json
from pathlib import Path

from .engine import headers, read_ledger
from .store import DB, check, load_game, load_ref, read_csv

EXOGENOUS = ("population", "buildings", "goods")


def _table(rows: list[dict], cols: list[str] | None = None) -> dict:
    cols = cols or (list(rows[0]) if rows else [])
    return {"cols": cols, "rows": [[r.get(c, "") for c in cols] for r in rows]}


def collect(root: Path = DB) -> dict:
    ref = load_ref(root)
    games = {}
    for path in sorted((root / "games").glob("*/game.toml")):
        game = load_game(path.parent.name, ref, root)
        errors, gaps = check(ref, game)
        games[path.parent.name] = {
            "name": game.name, "seed": game.seed, "promotion_months": game.promotion_months,
            "params": game.params,
            "ledger": {n: _table(read_ledger(game, n), cols) for n, cols in headers(ref).items()},
            "exogenous": {n: _table(read_csv(path.parent / f"exogenous/{n}.csv")) for n in EXOGENOUS},
            "errors": errors, "gaps": gaps,
        }
    return {"games": games}


def build(out: Path, root: Path = DB) -> Path:
    data = json.dumps(collect(root), separators=(",", ":")).replace("</", "<\\/")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(PAGE.replace("/*DATA*/null", data), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    return out / "index.html"


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Umpire's database</title>
<style>
:root {
  --bg: #f6f5f1; --panel: #ffffff; --ink: #1c1b18; --muted: #6b675e; --line: #dedbd2;
  --accent: #7a3b12; --accent-bg: #f3e6da; --neg: #a3261b; --warn-bg: #fbf1d6; --warn-ink: #6a4a00;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161513; --panel: #1f1e1b; --ink: #ebe8e0; --muted: #a09b8f; --line: #36332d;
    --accent: #e0a070; --accent-bg: #3a2a1c; --neg: #f08a7c; --warn-bg: #3a3014; --warn-ink: #f0d58a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 10px 16px; }
.bar { max-width: 1180px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; }
h1 { font-size: 17px; margin: 0; font-weight: 650; letter-spacing: -0.01em; }
.spacer { flex: 1; }
select, button { font: inherit; color: inherit; background: var(--bg); border: 1px solid var(--line);
  border-radius: 6px; padding: 5px 10px; }
button { cursor: pointer; min-width: 36px; }
button:disabled { opacity: .35; cursor: default; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.tick { display: flex; gap: 6px; align-items: center; }
main { max-width: 1180px; margin: 0 auto; padding: 16px 16px 60px; }
.meta { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
nav { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 18px; }
nav a { text-decoration: none; color: var(--muted); font-size: 13px; padding: 3px 9px;
  border: 1px solid var(--line); border-radius: 999px; background: var(--panel); }
nav a:hover { color: var(--accent); border-color: var(--accent); }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  margin: 0 0 16px; scroll-margin-top: 70px; }
section > h2 { font-size: 14px; margin: 0; padding: 11px 14px; font-weight: 650; }
section > h2 small { font-weight: 400; color: var(--muted); margin-left: 8px; }
section > p { margin: 0; padding: 0 14px 12px; color: var(--muted); font-size: 13px; }
.scroll { overflow-x: auto; border-top: 1px solid var(--line); }
table { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 12px; white-space: nowrap; text-align: right; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; font-size: 12px; position: sticky; top: 0; background: var(--panel); }
th.t, td.t { text-align: left; }
tr:last-child td { border-bottom: 0; }
tr.now td { background: var(--accent-bg); }
tr.pick { cursor: pointer; }
tr.pick:hover td { background: var(--accent-bg); }
td.neg { color: var(--neg); }
.empty { padding: 12px 14px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); }
ul.notes { margin: 0; padding: 10px 14px 12px 32px; border-top: 1px solid var(--line); font-size: 13px; }
ul.notes li { margin: 3px 0; overflow-wrap: anywhere; }
ul.warn { background: var(--warn-bg); color: var(--warn-ink); border-radius: 0 0 10px 10px; }
</style>
</head>
<body>
<header><div class="bar">
  <h1>Umpire's database</h1>
  <select id="game" aria-label="Game"></select>
  <span class="spacer"></span>
  <div class="tick">
    <button id="prev" aria-label="Previous tick">&larr;</button>
    <select id="tick" aria-label="Tick"></select>
    <button id="next" aria-label="Next tick">&rarr;</button>
  </div>
</div></header>
<main id="main"></main>
<script>
const DATA = /*DATA*/null;
const $ = id => document.getElementById(id);
const TEXT = new Set(["tick", "until", "class", "building", "owner", "good", "group", "variable",
  "source", "scope", "note", "message", "level"]);
let game, tick;

function num(v) {
  if (v === "" || v === null || v === undefined) return "";
  const n = Number(v);
  if (!isFinite(n)) return v;
  const a = Math.abs(n);
  return n.toLocaleString("en-US", { maximumFractionDigits: a !== 0 && a < 1 ? 4 : 2 });
}
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const k in attrs || {}) k === "class" ? e.className = attrs[k] : e.setAttribute(k, attrs[k]);
  for (const k of kids) e.append(k);
  return e;
}
function table(cols, rows, opts = {}) {
  if (!rows.length) return el("div", { class: "empty" }, opts.empty || "Nothing this tick.");
  const head = el("tr", {}, ...cols.map(c => el("th", { class: TEXT.has(c) ? "t" : "" }, c.replace(/_/g, " "))));
  const body = rows.map(r => {
    const tr = el("tr", {}, ...cols.map((c, i) => {
      const text = TEXT.has(c), v = r[i];
      const neg = !text && Number(v) < 0;
      return el("td", { class: text ? "t" : neg ? "neg" : "" }, text ? String(v ?? "") : num(v));
    }));
    if (opts.pick) {
      tr.classList.add("pick");
      if (r[0] === tick) tr.classList.add("now");
      tr.addEventListener("click", () => { tick = r[0]; render(); });
    }
    return tr;
  });
  return el("div", { class: "scroll" }, el("table", {}, el("thead", {}, head), el("tbody", {}, ...body)));
}
function section(id, title, note, ...body) {
  const h = el("h2", {}, title);
  if (note) h.append(el("small", {}, note));
  return el("section", { id }, h, ...body);
}
function at(g, name) {
  const t = g.ledger[name], i = t.cols.indexOf("tick");
  return { cols: t.cols.filter(c => c !== "tick"), rows: t.rows.filter(r => r[i] === tick).map(r => r.filter((_, j) => j !== i)) };
}
function pivot(t, rowKey, colKey, valKey) {
  const ri = t.cols.indexOf(rowKey), ci = t.cols.indexOf(colKey), vi = t.cols.indexOf(valKey);
  const cols = [...new Set(t.rows.map(r => r[ci]))], map = new Map();
  for (const r of t.rows) { if (!map.has(r[ri])) map.set(r[ri], {}); map.get(r[ri])[r[ci]] = r[vi]; }
  return { cols: [rowKey, ...cols], rows: [...map].map(([k, v]) => [k, ...cols.map(c => v[c] ?? "")]) };
}
function active(t) {       // exogenous rows in force at this tick
  const ti = t.cols.indexOf("tick"), ui = t.cols.indexOf("until");
  return t.rows.filter(r => r[ti] <= tick && (ui < 0 ? r[ti] === tick : (!r[ui] || tick <= r[ui])));
}

function render() {
  const g = DATA.games[game], main = $("main");
  const ticks = g.ledger.indicators.rows.map(r => r[0]);
  if (!ticks.includes(tick)) tick = ticks[ticks.length - 1];
  $("tick").replaceChildren(...ticks.map(t => el("option", t === tick ? { selected: "" } : {}, t)));
  const i = ticks.indexOf(tick);
  $("prev").disabled = i <= 0; $("next").disabled = i < 0 || i >= ticks.length - 1;
  $("prev").onclick = () => { tick = ticks[i - 1]; render(); };
  $("next").onclick = () => { tick = ticks[i + 1]; render(); };
  history.replaceState(null, "", "#" + encodeURIComponent(game) + (tick ? "/" + tick : ""));
  main.replaceChildren();
  if (!ticks.length) { main.append(el("p", { class: "meta" }, "No ticks resolved yet for this game.")); return; }

  const p = g.params;
  main.append(el("p", { class: "meta" },
    `${g.name} · seed ${g.seed} · promotions in months ${g.promotion_months.join(", ")} · upgrade mode ${p.upgrade_mode}` +
    ` · capital depreciation ${p.capital_depreciation}/tick · construction priority ${p.construction_priority.length ? p.construction_priority.join(" > ") : "pro rata"}`));

  const cons = at(g, "consumption"), warns = at(g, "warnings").rows;
  const parts = [
    ["indicators", "Headline indicators", "all ticks; click a row to jump",
      table(g.ledger.indicators.cols, g.ledger.indicators.rows, { pick: true }),
      el("p", {}, "")],
    ["population", "Population", "working-age stock by class", table(...Object.values(at(g, "population")))],
    ["labour", "Labour", "jobs against people, by class", table(...Object.values(at(g, "labour")))],
    ["buildings", "Buildings", "size, capital pool and value at foreign prices", table(...Object.values(at(g, "buildings")))],
    ["levels", "Building levels", "operating = ran this tick; units = standing at its end", table(...Object.values(at(g, "building_levels")))],
    ["construction", "Construction works", "wanted against capacity", table(...Object.values(at(g, "construction")), { empty: "No works outstanding this tick." })],
    ["goods", "Goods markets", "supply, demand by use, balance", table(...Object.values(at(g, "goods_market")))],
    ["bundle-qty", "Household bundles", "quantity by class and demand group", table(...Object.values(pivot(cons, "class", "group", "qty")))],
    ["bundle-cost", "Bundle cost", "blank where a demand group has no goods mapped", table(...Object.values(pivot(cons, "class", "group", "cost")))],
    ["orders", "Building orders booked", "events applied this tick", table(...Object.values(at(g, "investment")), { empty: "No building events this tick." })],
  ];
  for (const n of ["population", "goods", "buildings"]) {
    const t = g.exogenous[n];
    parts.push(["exo-" + n, "Exogenous: " + n, n === "buildings" ? "events dated this tick" : "rows in force this tick",
      table(t.cols, active(t), { empty: "None." })]);
  }
  parts.push(["warnings", "Warnings this tick", "", warns.length
    ? el("ul", { class: "notes warn" }, ...warns.map(r => el("li", {}, r[0]))) : el("div", { class: "empty" }, "None.")]);
  const gaps = [...g.errors.map(e => "Error: " + e), ...g.gaps];
  parts.push(["gaps", "Data gaps", "what the tables still lack", gaps.length
    ? el("ul", { class: "notes" }, ...gaps.map(x => el("li", {}, x))) : el("div", { class: "empty" }, "None.")]);

  main.append(el("nav", {}, ...parts.map(([id, title]) => el("a", { href: "#" + id }, title))));
  for (const [id, title, note, ...body] of parts) {
    const s = section(id, title, note, ...body.filter(b => b.tagName !== "P" || b.textContent));
    main.append(s);
  }
  main.querySelectorAll("nav a").forEach(a => a.addEventListener("click", e => {
    e.preventDefault(); $(a.getAttribute("href").slice(1)).scrollIntoView({ behavior: "smooth" });
  }));
}

const names = Object.keys(DATA.games);
const [hg, ht] = decodeURIComponent(location.hash.slice(1)).split("/");
game = names.includes(hg) ? hg : names[0]; tick = ht;
$("game").replaceChildren(...names.map(n => el("option", { value: n, ...(n === game ? { selected: "" } : {}) }, DATA.games[n].name)));
$("game").hidden = names.length < 2;
$("game").onchange = e => { game = e.target.value; tick = null; render(); };
$("tick").onchange = e => { tick = e.target.value; render(); };
if (game) render(); else $("main").append(el("p", { class: "meta" }, "No games under db/games yet."));
</script>
</body>
</html>
"""
