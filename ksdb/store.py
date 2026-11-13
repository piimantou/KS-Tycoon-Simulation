"""Storage layer: CSV/TOML in, CSV out, plus reference-data loading and checks.

Everything the umpire edits is plain text under ``db/`` so that git is the
history and GitHub renders the tables.
"""
from __future__ import annotations

import csv
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "db"

POP_VARS = ("births", "deaths", "migration", "promotion_rate", "dependency")
GOODS_VARS = ("foreign_price", "output_modifier")
TICK_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ---------------------------------------------------------------- csv helpers
def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = []
        for row in csv.DictReader(f):
            clean = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if any(clean.values()):
                rows.append(clean)
        return rows


def fmt(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, str):
        return v
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow([fmt(r.get(h)) for h in header])


def num(s, default: float = 0.0) -> float:
    return default if s in ("", None) else float(s)


# ------------------------------------------------------------- reference data
@dataclass
class Recipe:
    building: str
    level: int
    inputs: dict[str, float]
    labour: dict[str, float]
    capital: dict[str, float]
    outputs: dict[str, float]
    construction: float         # construction units to bring one unit up to this level
    defined: bool               # has labour figures, so it can operate
    blank_qty: list[str]        # goods named without a quantity


@dataclass
class Ref:
    classes: list[str]
    goods: list[str]
    capital: dict[str, str]                         # K1 -> good
    groups: list[str]
    weights: dict[str, dict[str, float]]            # class -> group -> weight
    group_goods: dict[str, list[tuple[str, float]]]
    recipes: dict[str, list[Recipe]]                # building -> levels, ascending
    params: dict

    def usable(self, building: str) -> list[Recipe]:
        """Levels a building can climb: contiguous defined levels from the bottom."""
        out = []
        for r in self.recipes.get(building, []):
            if not r.defined:
                break
            out.append(r)
        return out


def load_ref(root: Path = DB) -> Ref:
    ref = root / "ref"
    classes = [r["class"] for r in read_csv(ref / "classes.csv")]
    goods_rows = read_csv(ref / "goods.csv")
    capital = {r["capital"]: r["good"] for r in goods_rows if r.get("capital")}
    wrows = read_csv(ref / "consumption_weights.csv")
    groups = [k for k in (wrows[0] if wrows else {}) if k != "class"]
    weights = {r["class"]: {g: num(r[g]) for g in groups} for r in wrows}
    group_goods: dict[str, list] = {}
    for r in read_csv(ref / "demand_group_goods.csv"):
        group_goods.setdefault(r["group"], []).append((r["good"], num(r["share"])))

    recipes: dict[str, list[Recipe]] = {}
    for r in read_csv(ref / "recipes.csv"):
        def pairs(prefix):
            named, blank = {}, []
            for k in r:
                m = re.fullmatch(prefix + r"(\d+)_good", k)
                if m and r[k]:
                    q = r.get(f"{prefix}{m.group(1)}_qty", "")
                    named[r[k]] = num(q)
                    if q == "":
                        blank.append(r[k])
            return named, blank
        inputs, b1 = pairs("in")
        outputs, b2 = pairs("out")
        rec = Recipe(
            building=r["building"], level=int(num(r["level"])),
            inputs=inputs, outputs=outputs,
            labour={c: num(r[c]) for c in classes if r.get(c, "") != ""},
            capital={k: num(r[k]) for k in capital if r.get(k, "") != ""},
            construction=num(r.get("construction")),
            defined=any(r.get(c, "") != "" for c in classes),
            blank_qty=b1 + b2,
        )
        recipes.setdefault(rec.building, []).append(rec)
    for levels in recipes.values():
        levels.sort(key=lambda x: x.level)

    with open(ref / "params.toml", "rb") as f:
        params = tomllib.load(f)
    return Ref(classes, [r["good"] for r in goods_rows], capital, groups, weights,
               group_goods, recipes, params)


# ----------------------------------------------------------------------- game
@dataclass
class Setting:
    tick: str
    until: str
    scope: str
    value: float
    idx: int


@dataclass
class Game:
    path: Path
    name: str
    start: str
    seed: int
    promotion_months: list[int]
    params: dict
    setup_pop: dict[str, int]
    setup_bld: list[dict]
    pop: dict[str, list[Setting]] = field(default_factory=dict)     # variable -> settings
    goods: dict[str, list[Setting]] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)                # building events

    @property
    def ledger(self) -> Path:
        return self.path / "ledger"


def game_path(name: str, root: Path = DB) -> Path:
    p = Path(name)
    return p if (p / "game.toml").exists() else root / "games" / name


def _settings(rows: list[dict], scope_col: str) -> dict[str, list[Setting]]:
    out: dict[str, list[Setting]] = {}
    for i, r in enumerate(rows):
        out.setdefault(r["variable"], []).append(
            Setting(r["tick"], r.get("until", ""), r.get(scope_col) or "*", num(r["value"]), i))
    return out


def load_game(name: str, ref: Ref, root: Path = DB) -> Game:
    path = game_path(name, root)
    with open(path / "game.toml", "rb") as f:
        cfg = tomllib.load(f)
    return Game(
        path=path, name=cfg.get("name", path.name), start=cfg["start"],
        seed=int(cfg.get("seed", 0)),
        promotion_months=list(cfg.get("promotion_months", range(1, 13))),
        params={**ref.params, **cfg.get("params", {})},
        setup_pop={r["class"]: int(num(r["stock"])) for r in read_csv(path / "setup/population.csv")},
        setup_bld=read_csv(path / "setup/buildings.csv"),
        pop=_settings(read_csv(path / "exogenous/population.csv"), "class"),
        goods=_settings(read_csv(path / "exogenous/goods.csv"), "scope"),
        events=read_csv(path / "exogenous/buildings.csv"),
    )


def resolve(settings: dict[str, list[Setting]], tick: str, variable: str, scope: str,
            default: float) -> float:
    """Value of an exogenous setting at ``tick``.

    A row applies from its ``tick`` onward; with ``until`` it applies only
    through that tick (a shock) and then lapses. An active shock beats any
    open-ended row; otherwise the most recent start wins, then a named scope
    over ``*``, then the later row in the file.
    """
    best = None
    for s in settings.get(variable, ()):
        if s.scope not in (scope, "*") or s.tick > tick or (s.until and tick > s.until):
            continue
        key = (bool(s.until), s.tick, s.scope != "*", s.idx)
        if best is None or key > best[0]:
            best = (key, s.value)
    return best[1] if best else default


# --------------------------------------------------------------------- checks
def check(ref: Ref, game: Game | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, gaps). Errors are broken references; gaps are unfilled data."""
    errors, gaps = [], []
    goods, known_b = set(ref.goods), set(ref.recipes)

    for c in ref.classes:
        if c not in ref.weights:
            errors.append(f"consumption_weights.csv has no row for class {c}")
    for g, pairs in ref.group_goods.items():
        if g not in ref.groups:
            errors.append(f"demand_group_goods.csv: unknown group {g!r}")
        for good, _ in pairs:
            if good not in goods:
                errors.append(f"demand_group_goods.csv: unknown good {good!r}")
        total = sum(s for _, s in pairs)
        if abs(total - 1) > 1e-6:
            errors.append(f"demand_group_goods.csv: shares for {g} sum to {total:g}, not 1")
    unmapped = [g for g in ref.groups if g not in ref.group_goods]
    if unmapped:
        gaps.append("demand groups with no goods mapped (tracked, but put no demand on "
                    "goods markets): " + ", ".join(unmapped))

    produced, empty, blanks = set(), [], []
    for b, levels in ref.recipes.items():
        for r in levels:
            for good in list(r.inputs) + list(r.outputs):
                if good not in goods:
                    errors.append(f"recipes.csv: {b} L{r.level} uses unknown good {good!r}")
            if r.defined:
                produced.update(r.outputs)
                if r.blank_qty:
                    blanks.append(f"{b} L{r.level} ({', '.join(r.blank_qty)})")
        if not ref.usable(b):
            empty.append(b)
        elif len(ref.usable(b)) < len(levels):
            gaps.append(f"{b}: only levels 1-{len(ref.usable(b))} of {len(levels)} have labour figures")
    if empty:
        gaps.append(f"{len(empty)} of {len(ref.recipes)} buildings have no recipe yet: " + ", ".join(empty))
    if blanks:
        gaps.append("recipes naming a good without a quantity (treated as 0): " + "; ".join(blanks))
    cgood = ref.params.get("construction_good", "")
    if cgood and cgood not in goods:
        errors.append(f"params.toml: construction_good {cgood!r} is not in goods.csv")
    if not any(r.construction for lv in ref.recipes.values() for r in lv):
        gaps.append("no recipe has a `construction` cost, so building and upgrading are free "
                    "and construction capacity never binds")
    orphans = [g for g in ref.goods if g not in produced]
    if orphans:
        gaps.append("goods no defined recipe produces: " + ", ".join(orphans))

    if game:
        for label, settings, valid, scopes in (
            ("population", game.pop, POP_VARS, set(ref.classes)),
            ("goods", game.goods, GOODS_VARS, goods | known_b),
        ):
            for var, rows in settings.items():
                if var not in valid:
                    errors.append(f"exogenous/{label}.csv: unknown variable {var!r}")
                for s in rows:
                    if s.scope != "*" and s.scope not in scopes:
                        errors.append(f"exogenous/{label}.csv: unknown scope {s.scope!r}")
                    for t in (s.tick, s.until):
                        if t and not TICK_RE.match(t):
                            errors.append(f"exogenous/{label}.csv: bad tick {t!r} (want YYYY-MM)")
        for e in game.events + game.setup_bld:
            if e["building"] not in known_b:
                errors.append(f"buildings: unknown building {e['building']!r}")
            if "variable" in e and e["variable"] != "size" and e["variable"] not in ref.capital:
                errors.append(f"exogenous/buildings.csv: unknown variable {e['variable']!r}")
            if "tick" in e and not TICK_RE.match(e["tick"]):
                errors.append(f"exogenous/buildings.csv: bad tick {e['tick']!r} (want YYYY-MM)")
        for c in game.setup_pop:
            if c not in ref.classes:
                errors.append(f"setup/population.csv: unknown class {c!r}")
        unpriced = [g for g in ref.goods if not any(
            s.scope in (g, "*") for s in game.goods.get("foreign_price", ()))]
        if unpriced:
            gaps.append("goods with no foreign_price (their flows are valued at 0): " + ", ".join(unpriced))
    return errors, gaps
