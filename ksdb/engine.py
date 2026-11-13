"""The monthly tick: state(t) = f(state(t-1), exogenous(t)).

Only what the Umpire's Guide and the Economic Tables workbook specify is
computed. Wages, profit distribution, the government budget and standard of
living are deliberately absent; the ledger stops at the quantities any model
of them would need (value added per building, bundle cost per class, labour
balance per class).
"""
from __future__ import annotations

import copy
import hashlib
import math
import random
from collections import defaultdict
from dataclasses import dataclass

from .store import Game, Ref, read_csv, resolve, write_csv, num

EPS = 1e-9


@dataclass
class State:
    pop: dict[str, int]         # class -> working-age stock
    bld: dict[tuple, dict]      # (building, owner) -> {"size": ordered units, "K": capital pool,
                                #                       "lv": {level: [built units, banked construction]}}


def next_tick(t: str) -> str:
    y, m = int(t[:4]), int(t[5:])
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}"


def rng_for(seed: int, tick: str, stream: str) -> random.Random:
    """One independent, reproducible stream per (game, tick, purpose)."""
    h = hashlib.sha256(f"{seed}|{tick}|{stream}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def ladder(size: float, pool: dict[str, float], levels, mode: str) -> dict[int, float]:
    """The level mix ``size`` units could hold given the building's capital pool.

    A recipe's K columns are the capital one unit must hold to run at that
    level. Capital is spent bottom-up: every unit reaches level n before any
    reaches n+1. ``mode`` sets the grain: "continuous" (fractional units),
    "unit" (whole units only) or "building" (all units or none).
    """
    out: dict[int, float] = {}
    left = dict(pool)
    n_prev, req_prev, lvl_prev = size, {}, None
    for r in levels:
        need = {k: r.capital.get(k, 0) - req_prev.get(k, 0) for k in r.capital}
        need = {k: v for k, v in need.items() if v > EPS}
        n = n_prev
        if need:
            n = min(n_prev, min(left.get(k, 0) / v for k, v in need.items()))
            if mode == "unit":
                n = float(math.floor(n + EPS))
            elif mode == "building":
                n = n_prev if n >= n_prev - EPS else 0.0
            for k, v in need.items():
                left[k] = left.get(k, 0) - n * v
        if lvl_prev is not None and n_prev - n > EPS:
            out[lvl_prev] = n_prev - n
        n_prev, req_prev, lvl_prev = n, r.capital, r.level
        if n <= EPS:
            break
    if lvl_prev is not None and n_prev > EPS:
        out[lvl_prev] = n_prev
    return out


def step(ref: Ref, game: Game, tick: str, prev: State | None) -> tuple[State, dict[str, list[dict]]]:
    """Resolve one tick. ``prev`` is None for the opening tick (stocks, no flows)."""
    P, classes, caps = game.params, ref.classes, list(ref.capital)
    mode = P["upgrade_mode"]
    start = prev is None
    warn: list[str] = []
    T: dict[str, list[dict]] = defaultdict(list)

    # ---- 1. population: promotions (binomial), then births / deaths / migration
    promo_on = not start and int(tick[5:]) in game.promotion_months
    rng = rng_for(game.seed, tick, "promotion")
    rate = {c: resolve(game.pop, tick, "promotion_rate", c, 0.0) for c in classes}
    out_ = {c: 0 for c in classes}
    if promo_on:
        for c in classes[:-1]:
            if prev.pop[c] > 0 and rate[c] > 0:
                out_[c] = rng.binomialvariate(prev.pop[c], min(1.0, rate[c]))
    pop, dep = {}, {}
    for i, c in enumerate(classes):
        dep[c] = resolve(game.pop, tick, "dependency", c, 0.0)
        flows = {"births": 0, "deaths": 0, "migration": 0}
        inn = out_[classes[i - 1]] if i else 0
        if start:
            stock = game.setup_pop.get(c, 0)
        else:
            flows = {k: int(round(resolve(game.pop, tick, k, c, 0.0))) for k in flows}
            stock = prev.pop[c] - out_[c] + inn + flows["births"] - flows["deaths"] + flows["migration"]
            if stock < 0:
                warn.append(f"{c}: outflows exceeded the stock by {-stock}; clamped to 0")
                stock = 0
        pop[c] = stock
        T["population"].append({
            "tick": tick, "class": c, "stock": stock, **flows, "promoted_in": inn,
            "promoted_out": out_[c], "promotion_rate": rate[c] if i < len(classes) - 1 else "",
            "dependency": dep[c], "dependents": stock * dep[c]})

    # ---- 2. buildings: wear the pool, then book this tick's orders (size, capital)
    price = {g: resolve(game.goods, tick, "foreign_price", g, None) for g in ref.goods}
    unpriced: set[str] = set()

    def value(good: str, qty: float) -> float:
        if price[good] is None:
            if abs(qty) > EPS:
                unpriced.add(good)
            return 0.0
        return qty * price[good]

    blank = lambda: {"size": 0.0, "K": {k: 0.0 for k in caps}, "lv": {}}
    if start:
        bld = {}
        for r in game.setup_bld:
            e = bld.setdefault((r["building"], r["owner"]), blank())
            e["size"] += num(r.get("size"))
            for k in caps:
                e["K"][k] += num(r.get(k))
        for (b, o), e in bld.items():       # the opening stock is already built
            e["lv"] = {l: [n, 0.0] for l, n in ladder(e["size"], e["K"], ref.usable(b), mode).items()}
    else:
        bld = copy.deepcopy(prev.bld)
        for e in bld.values():
            for k in caps:
                e["K"][k] *= 1 - P["capital_depreciation"]
    invest: dict[str, float] = defaultdict(float)
    for ev in game.events:
        if ev["tick"] != tick or ev["building"] not in ref.recipes:
            continue
        e = bld.setdefault((ev["building"], ev["owner"]), blank())
        var, v = ev["variable"], num(ev["value"])
        cost = 0.0
        if var == "size":
            e["size"] = max(0.0, e["size"] + v)
        elif var in caps:
            e["K"][var] = max(0.0, e["K"][var] + v)
            if v > 0:
                invest[ref.capital[var]] += v
                cost = value(ref.capital[var], v)
        T["investment"].append({"tick": tick, "building": ev["building"], "owner": ev["owner"],
                                "variable": var, "value": v, "source": ev.get("source", ""),
                                "capital_cost": cost})
    recipe = {(b, r.level): r for b, lv in ref.recipes.items() for r in lv}
    # What runs this tick is what stood at the start of it; this tick's works finish at its end.
    operating = {key: {l: u for l, (u, _) in e["lv"].items() if u > EPS} for key, e in bld.items()}

    # ---- 3. labour: each class fills its own jobs, then surplus cascades downward
    demand = {c: 0.0 for c in classes}
    for (b, o), lv in operating.items():
        for level, n in lv.items():
            for c, q in recipe[b, level].labour.items():
                demand[c] += n * q
    filled = {c: min(pop[c], demand[c]) for c in classes}
    employed = dict(filled)
    if P["labour_downfill"]:
        for hi in reversed(range(len(classes))):
            for lo in reversed(range(hi)):
                h, l = classes[hi], classes[lo]
                take = min(demand[l] - filled[l], pop[h] - employed[h])
                filled[l] += take
                employed[h] += take
    ratio = {c: filled[c] / demand[c] if demand[c] > EPS else 1.0 for c in classes}
    for c in classes:
        T["labour"].append({"tick": tick, "class": c, "supply": pop[c], "demand": demand[c],
                            "jobs_filled": filled[c], "employed": employed[c],
                            "unemployed": pop[c] - employed[c], "vacancies": demand[c] - filled[c]})

    # ---- 4. production: Leontief, throttled by the scarcest labour class
    produced, intermediate = defaultdict(float), defaultdict(float)
    ran: dict[tuple, dict] = {}
    tot_out = tot_in = 0.0
    for (b, o), lv in sorted(operating.items()):
        mod_b = resolve(game.goods, tick, "output_modifier", b, 1.0)
        out_val = in_cost = 0.0
        for level, n in sorted(lv.items()):
            r = recipe[b, level]
            staffing = min((ratio[c] for c, q in r.labour.items() if q > 0), default=1.0)
            run = n * staffing
            for g, q in r.outputs.items():
                x = q * run * mod_b * resolve(game.goods, tick, "output_modifier", g, 1.0)
                produced[g] += x
                out_val += value(g, x)
            for g, q in r.inputs.items():
                intermediate[g] += q * run
                in_cost += value(g, q * run)
            if r.blank_qty and run > EPS:
                warn.append(f"{b} L{level} is running but has no quantity for: {', '.join(r.blank_qty)}")
            ran[b, o, level] = {"operating": n, "jobs": n * sum(r.labour.values()), "staffing": staffing}
        e = bld[b, o]
        T["buildings"].append({"tick": tick, "building": b, "owner": o, "size": e["size"],
                               **e["K"], "output_value": out_val, "input_cost": in_cost,
                               "value_added": out_val - in_cost})
        tot_out, tot_in = tot_out + out_val, tot_in + in_cost

    # ---- 5. construction: this tick's Construction output is the most that can be built.
    # Works are whatever separates each building from the level mix its size and
    # capital pool allow; a unit climbs at most one level per tick.
    cgood = P.get("construction_good", "")
    capacity = produced.get(cgood, 0.0)
    works = []
    for (b, o), e in sorted(bld.items()):
        usable = ref.usable(b)
        lvls = [r.level for r in usable]
        target = ladder(e["size"], e["K"], usable, mode)
        at_least = lambda d, i: sum(d.get(l, 0.0) for l in lvls[i:])
        built = {l: u for l, (u, _) in e["lv"].items()}
        tgt = [at_least(target, i) for i in range(len(lvls))]
        cur = [min(at_least(built, i), tgt[i]) for i in range(len(lvls))]   # lost capital demotes at once
        idle = e["size"] - (tgt[0] if tgt else 0.0)
        if idle > EPS:
            why = "no recipe with labour figures" if not usable else "level 1 capital not met"
            warn.append(f"{b} ({o}): {idle:g} unit(s) cannot be built - {why}")
        base = [e["size"]] + cur[:-1]
        e["_cur"], e["_bank"] = cur, {}
        for i, r in enumerate(usable):
            want = min(tgt[i], base[i]) - cur[i]
            if want > EPS:
                bank = e["lv"].get(r.level, [0, 0.0])[1]
                works.append({"key": (b, o), "i": i, "r": r, "want": want, "bank": bank,
                              "need": max(0.0, want * r.construction - bank), "got": 0.0})
    order = list(P.get("construction_priority", []))
    tiers = [[w for w in works if w["key"][1] == o] for o in order]
    tiers.append([w for w in works if w["key"][1] not in order])
    left = capacity
    for tier in tiers:
        need = sum(w["need"] for w in tier)
        share = min(1.0, left / need) if need > EPS else 0.0
        for w in tier:
            w["got"] = w["need"] * share
        left -= need * share
    for w in works:
        e, r, cost = bld[w["key"]], w["r"], w["r"].construction
        banked = w["bank"] + w["got"]
        if cost <= EPS:
            done = w["want"]
        elif mode == "continuous":
            done = min(w["want"], banked / cost)
            banked = 0.0
        else:                       # lumpy: bank construction until a whole grain is paid for
            grain = min(1.0, w["want"]) if mode == "unit" else w["want"]
            done = min(w["want"], math.floor(banked / (grain * cost) + EPS) * grain)
            banked -= done * cost
        e["_cur"][w["i"]] += done
        if banked > EPS:
            e["_bank"][r.level] = banked
        T["construction"].append({"tick": tick, "building": w["key"][0], "owner": w["key"][1],
                                  "level": r.level, "units_wanted": w["want"],
                                  "construction_wanted": w["need"], "construction_done": w["got"],
                                  "units_built": done})
    backlog = sum(w["need"] - w["got"] for w in works)
    if backlog > EPS and capacity <= EPS:
        warn.append(f"{backlog:g} construction unit(s) wanted but no {cgood or 'construction good'} was produced")
    for (b, o), e in sorted(bld.items()):
        cur, bank = e.pop("_cur"), e.pop("_bank")
        lvls = [r.level for r in ref.usable(b)]
        e["lv"] = {}
        for i, l in enumerate(lvls):
            u = cur[i] - (cur[i + 1] if i + 1 < len(cur) else 0.0)
            if u > EPS or bank.get(l, 0) > EPS:
                e["lv"][l] = [max(u, 0.0), bank.get(l, 0.0)]
        for l in sorted(set(e["lv"]) | {k[2] for k in ran if k[:2] == (b, o)}):
            T["building_levels"].append({
                "tick": tick, "building": b, "owner": o, "level": l,
                **ran.get((b, o, l), {"operating": 0, "jobs": 0, "staffing": ""}),
                "units": e["lv"].get(l, [0, 0])[0], "banked_construction": e["lv"].get(l, [0, 0])[1]})
        if (b, o) not in operating or not operating[b, o]:
            T["buildings"].append({"tick": tick, "building": b, "owner": o, "size": e["size"],
                                   **e["K"], "output_value": 0, "input_cost": 0, "value_added": 0})
    if cgood in ref.goods:
        invest[cgood] += sum(w["need"] for w in works)

    # ---- 6. consumption: fixed bundles; prices only decide what they cost
    household = defaultdict(float)
    spend = 0.0
    for c in classes:
        for g in ref.groups:
            qty = pop[c] * ref.weights[c][g] * (1 + dep[c]) * P["bundle_scale"]
            cost = ""
            if g in ref.group_goods:
                cost = 0.0
                for good, share in ref.group_goods[g]:
                    household[good] += qty * share
                    cost += value(good, qty * share)
                spend += cost
            T["consumption"].append({"tick": tick, "class": c, "group": g, "qty": qty, "cost": cost})

    # ---- 7. goods markets: supply, demand by use, balance
    net = 0.0
    for g in ref.goods:
        dem = intermediate[g] + household[g] + invest[g]
        bal = produced[g] - dem
        net += value(g, bal)
        T["goods_market"].append({
            "tick": tick, "good": g, "price": price[g], "supply": produced[g],
            "intermediate": intermediate[g], "household": household[g], "investment": invest[g],
            "demand": dem, "balance": bal, "balance_value": value(g, bal)})
    if unpriced:
        warn.append("no foreign_price, valued at 0: " + ", ".join(sorted(unpriced)))

    # ---- 8. headline indicators
    total, working = sum(pop.values()), sum(employed.values())
    T["indicators"].append({
        "tick": tick, "population": total, "dependents": sum(pop[c] * dep[c] for c in classes),
        "jobs": sum(demand.values()), "employed": working,
        "unemployment_rate": (total - working) / total if total else 0.0,
        "output_value": tot_out, "input_cost": tot_in, "value_added": tot_out - tot_in,
        "household_spend": spend,
        "investment_value": sum(value(g, q) for g, q in invest.items()),
        "balance_value": net})
    T["buildings"].sort(key=lambda r: (r["building"], r["owner"]))
    T["warnings"] = [{"tick": tick, "message": m} for m in warn]
    return State(pop, bld), T


# --------------------------------------------------------------------- ledger
def headers(ref: Ref) -> dict[str, list[str]]:
    return {
        "indicators": ["tick", "population", "dependents", "jobs", "employed", "unemployment_rate",
                       "output_value", "input_cost", "value_added", "household_spend",
                       "investment_value", "balance_value"],
        "population": ["tick", "class", "stock", "births", "deaths", "migration", "promoted_in",
                       "promoted_out", "promotion_rate", "dependency", "dependents"],
        "labour": ["tick", "class", "supply", "demand", "jobs_filled", "employed", "unemployed",
                   "vacancies"],
        "buildings": ["tick", "building", "owner", "size", *ref.capital, "output_value",
                      "input_cost", "value_added"],
        "building_levels": ["tick", "building", "owner", "level", "operating", "jobs", "staffing",
                            "units", "banked_construction"],
        "construction": ["tick", "building", "owner", "level", "units_wanted",
                         "construction_wanted", "construction_done", "units_built"],
        "consumption": ["tick", "class", "group", "qty", "cost"],
        "goods_market": ["tick", "good", "price", "supply", "intermediate", "household",
                         "investment", "demand", "balance", "balance_value"],
        "investment": ["tick", "building", "owner", "variable", "value", "source", "capital_cost"],
        "warnings": ["tick", "message"],
    }


def read_ledger(game: Game, name: str) -> list[dict]:
    return read_csv(game.ledger / f"{name}.csv")


def last_tick(game: Game) -> str | None:
    rows = read_ledger(game, "indicators")
    return rows[-1]["tick"] if rows else None


def state_at(ref: Ref, game: Game, tick: str) -> State:
    """Rebuild the carried-forward stocks from the ledger rows of ``tick``."""
    pop = {r["class"]: int(num(r["stock"])) for r in read_ledger(game, "population") if r["tick"] == tick}
    bld = {(r["building"], r["owner"]): {"size": num(r["size"]), "K": {k: num(r[k]) for k in ref.capital},
                                          "lv": {}}
           for r in read_ledger(game, "buildings") if r["tick"] == tick}
    for r in read_ledger(game, "building_levels"):
        if r["tick"] == tick and (num(r["units"]) > EPS or num(r["banked_construction"]) > EPS):
            bld[r["building"], r["owner"]]["lv"][int(r["level"])] = [num(r["units"]),
                                                                     num(r["banked_construction"])]
    return State(pop, bld)


def advance(ref: Ref, game: Game, n: int = 1, replay: bool = False) -> list[str]:
    """Append ``n`` ticks to the ledger; ``replay`` recomputes it from the start instead.

    Past ticks are otherwise never recomputed: the ledger is the record, and
    editing a past input or a recipe changes history only on an explicit replay.
    """
    hdr = headers(ref)
    ledger = {name: ([] if replay else read_ledger(game, name)) for name in hdr}
    last = None if replay else last_tick(game)
    if replay:
        end = last_tick(game) or game.start
        n = 1 + (int(end[:4]) - int(game.start[:4])) * 12 + int(end[5:]) - int(game.start[5:])
    state = state_at(ref, game, last) if last else None
    done = []
    for _ in range(n):
        tick = next_tick(last) if last else game.start
        state, tables = step(ref, game, tick, state)
        for name in hdr:
            ledger[name].extend(tables.get(name, []))
        last = tick
        done.append(tick)
    for name, cols in hdr.items():
        write_csv(game.ledger / f"{name}.csv", cols, ledger[name])
    return done
