"""The annual financial-year tick.

``tick(state)`` is a pure function: it deep-copies the incoming state, applies
the ordered resolution below, and returns a :class:`TickResult` holding the new
state plus everything the handoff report needs. No randomness — campaigns are
fully reproducible.

Order of resolution
  1. advance projects (apply adjudicated effects on completion)
  2. size the manpower pool from readiness
  3. drain conscripted labour from non-essential sectors  (manpower -> economy)
  4. sector production -> supply + input demand
  5. pop consumption -> demand
  6. clear the floating market (prices)
  7. procurement: budget -> tokens (domestic gated by arms capacity)
  8. manpower gate: equipment + men -> Operational vs Training
  9. budget reconciliation (treasury / debt)
 10. standard of living -> loyalty -> stability
 11. recompute GDP, advance the year
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .config import Config
from . import market
from . import model as m


@dataclass
class TickResult:
    state: m.GameState
    warnings: list[str] = field(default_factory=list)
    operational_tokens: dict[str, int] = field(default_factory=dict)
    training_tokens: dict[str, int] = field(default_factory=dict)
    delivered: dict[str, dict] = field(default_factory=dict)   # token -> {domestic,import,cost}
    sector_output: dict[str, float] = field(default_factory=dict)
    prices: dict[str, float] = field(default_factory=dict)
    manpower_available: float = 0.0
    manpower_operational: float = 0.0
    personnel_cost: float = 0.0
    procurement_cost: float = 0.0
    project_cost: float = 0.0
    maintenance_load: float = 0.0


# --------------------------------------------------------------------------- #
def _apply_delta(state: m.GameState, d: m.StateDelta, warnings: list[str]) -> None:
    def op(cur: float) -> float:
        if d.op == "add":
            return cur + d.value
        if d.op == "mul":
            return cur * d.value
        if d.op == "set":
            return d.value
        warnings.append(f"unknown op '{d.op}' in delta {d.target}/{d.key}")
        return cur

    if d.target == "arms_capacity" and d.key in state.arms:
        state.arms[d.key].capacity = op(state.arms[d.key].capacity)
    elif d.target == "sector_efficiency" and d.key in state.sectors:
        state.sectors[d.key].efficiency = op(state.sectors[d.key].efficiency)
    elif d.target == "sector_labour" and d.key in state.sectors:
        state.sectors[d.key].labour = op(state.sectors[d.key].labour)
    elif d.target == "sector_productivity" and d.key in state.sectors:
        state.sectors[d.key].productivity = op(state.sectors[d.key].productivity)
    elif d.target == "good_base_price" and d.key in state.goods:
        state.goods[d.key].base_price = op(state.goods[d.key].base_price)
    elif d.target == "stability":
        state.stability = op(state.stability)
    else:
        warnings.append(f"delta target '{d.target}/{d.key}' had no effect")


def _advance_projects(state: m.GameState, warnings: list[str]) -> float:
    """Tick down lead times; apply effects on completion. Returns this year's
    project spend (allocations of projects newly started this year)."""
    spend = 0.0
    for pid in state.new_project_ids:
        if pid in state.projects:
            spend += state.projects[pid].allocation

    for proj in state.projects.values():
        if proj.remaining_years > 0:
            proj.remaining_years -= 1
            if proj.remaining_years == 0:
                for d in proj.effects:
                    _apply_delta(state, d, warnings)
                warnings.append(f"project completed: {proj.name}")
    return spend


def _manpower_pool(mp: m.Manpower) -> float:
    """Callable manpower by readiness level (cumulative tiers)."""
    base = mp.population * mp.volunteer_fraction
    if mp.readiness >= 3:
        base += mp.population * mp.conscription_i_fraction
    if mp.readiness >= 4:
        # general mobilisation: conscription II is the wider band (supersedes I)
        base = mp.population * (mp.volunteer_fraction + mp.conscription_ii_fraction)
    return base


def _drain_labour(state: m.GameState, pool: float, warnings: list[str]) -> None:
    """Active-forces manpower is pulled from non-essential sector labour."""
    nonessential = {sid: s for sid, s in state.sectors.items() if not s.essential}
    available = sum(s.labour for s in nonessential.values())
    if available <= 0:
        return
    drain = min(pool, available)
    if drain >= available and pool > available:
        warnings.append(
            "manpower call-up exceeds non-essential labour; economy fully stripped"
        )
    factor = 1.0 - (drain / available)
    for s in nonessential.values():
        s.labour *= factor


def _produce(state: m.GameState) -> tuple[dict[str, float], dict[str, float]]:
    supply: dict[str, float] = {}
    input_demand: dict[str, float] = {}
    for s in state.sectors.values():
        out = s.labour * s.productivity * s.efficiency
        if s.output_good:
            supply[s.output_good] = supply.get(s.output_good, 0.0) + out
        for gid, qty in s.inputs_per_output.items():
            input_demand[gid] = input_demand.get(gid, 0.0) + out * qty
    return supply, input_demand


def _consumption(state: m.GameState) -> dict[str, float]:
    demand: dict[str, float] = {}
    for pop in state.pops.values():
        for gid, per_cap in pop.needs_per_capita.items():
            demand[gid] = demand.get(gid, 0.0) + pop.size * per_cap
    return demand


def _procure(
    state: m.GameState, defense_remaining: float, warnings: list[str]
) -> tuple[dict[str, dict], float]:
    """Spend the defense budget on orders. Domestic orders are gated by arms
    capacity; imports by money. Mutates stockpile; returns (delivered, cost)."""
    delivered: dict[str, dict] = {}
    cap_left = {cid: c.capacity for cid, c in state.arms.items()}
    spent = 0.0

    for order in state.procurement_orders:
        unit = state.units.get(order.unit_token_id)
        if unit is None:
            warnings.append(f"order references unknown token '{order.unit_token_id}'")
            continue
        rec = delivered.setdefault(
            order.unit_token_id, {"domestic": 0, "import": 0, "cost": 0.0}
        )

        if order.channel == "domestic":
            price = unit.domestic_price
            if price is None:
                warnings.append(f"{unit.name}: no domestic production line")
                continue
            cap = cap_left.get(unit.category, 0.0)
            by_cap = int(cap)
            by_money = int((defense_remaining - spent) // price) if price > 0 else order.quantity
            qty = max(0, min(order.quantity, by_cap, by_money))
            if qty < order.quantity:
                lim = "arms capacity" if by_cap <= by_money else "budget"
                warnings.append(
                    f"{unit.name}: domestic order {order.quantity} -> {qty} "
                    f"(limited by {lim})"
                )
            cap_left[unit.category] = cap - qty
            rec["domestic"] += qty
        elif order.channel == "import":
            price = unit.import_price
            if price is None:
                warnings.append(f"{unit.name}: not available for import")
                continue
            by_money = int((defense_remaining - spent) // price) if price > 0 else order.quantity
            qty = max(0, min(order.quantity, by_money))
            if qty < order.quantity:
                warnings.append(
                    f"{unit.name}: import order {order.quantity} -> {qty} (limited by budget)"
                )
            rec["import"] += qty
        else:
            warnings.append(f"{unit.name}: unknown channel '{order.channel}'")
            continue

        cost = qty * price
        rec["cost"] += cost
        spent += cost
        state.stockpile.tokens[order.unit_token_id] = (
            state.stockpile.tokens.get(order.unit_token_id, 0) + qty
        )
    return delivered, spent


def _man_the_force(
    state: m.GameState, pool: float, cfg: Config, warnings: list[str]
) -> tuple[dict[str, int], dict[str, int], float, float, float]:
    """Allocate men to owned equipment. Equipment without men stays in Training.
    Returns (operational, training, personnel_cost, operational_men, maint_load)."""
    men_left = pool
    operational: dict[str, int] = {}
    training: dict[str, int] = {}
    operational_men = 0.0
    maint_load = 0.0

    for tid, owned in state.stockpile.tokens.items():
        unit = state.units.get(tid)
        if unit is None or owned <= 0:
            continue
        if unit.men_per_token <= 0:
            operational[tid] = owned
            maint_load += owned * unit.maintenance_tokens
            continue
        by_men = int(men_left // unit.men_per_token)
        op_n = min(owned, by_men)
        operational[tid] = op_n
        if op_n < owned:
            training[tid] = owned - op_n
        men_left -= op_n * unit.men_per_token
        operational_men += op_n * unit.men_per_token
        maint_load += op_n * unit.maintenance_tokens

    if any(training.values()):
        stuck = sum(training.values())
        warnings.append(
            f"{stuck} token(s) held in Training — insufficient manpower to operate "
            f"all delivered equipment"
        )

    # wages: volunteers at full wage, the rest (conscripts) at the reduced factor
    mp = state.manpower
    volunteer_cap = mp.population * mp.volunteer_fraction
    volunteers = min(operational_men, volunteer_cap)
    conscripts = max(0.0, operational_men - volunteers)
    personnel_cost = (
        volunteers * mp.base_wage
        + conscripts * mp.base_wage * cfg.conscript_wage_factor
    )
    return operational, training, personnel_cost, operational_men, maint_load


def _standard_of_living(
    state: m.GameState, supply: dict[str, float], demand: dict[str, float]
) -> None:
    """Update loyalty from how well goods demand is met, then roll up stability."""
    avail = {}
    for gid in set(list(supply) + list(demand)):
        d = demand.get(gid, 0.0)
        avail[gid] = 1.0 if d <= 0 else min(1.0, supply.get(gid, 0.0) / d)

    total_w = 0.0
    weighted = 0.0
    for pop in state.pops.values():
        if not pop.needs_per_capita:
            sat = 1.0
        else:
            sat = sum(avail.get(g, 1.0) for g in pop.needs_per_capita) / len(
                pop.needs_per_capita
            )
        pop.loyalty = 0.7 * pop.loyalty + 0.3 * sat   # drift toward satisfaction
        w = max(pop.political_weight, 1e-9)
        weighted += pop.loyalty * w
        total_w += w
    if total_w > 0:
        # blend prior stability with the politically-weighted loyalty
        state.stability = max(0.0, min(1.0, 0.5 * state.stability + 0.5 * (weighted / total_w)))


def _gdp(state: m.GameState, supply: dict[str, float]) -> float:
    total = 0.0
    for gid, qty in supply.items():
        good = state.goods.get(gid)
        if good:
            total += qty * good.price
    return total


# --------------------------------------------------------------------------- #
def tick(state: m.GameState, cfg: Config | None = None) -> TickResult:
    cfg = cfg or Config()
    s = copy.deepcopy(state)
    res = TickResult(state=s)
    w = res.warnings

    # 1. projects
    res.project_cost = _advance_projects(s, w)

    # 2-3. manpower pool + labour drain
    pool = _manpower_pool(s.manpower)
    res.manpower_available = pool
    _drain_labour(s, pool, w)

    # 4-5. production + demand
    supply, input_demand = _produce(s)
    demand = dict(input_demand)
    for gid, qty in _consumption(s).items():
        demand[gid] = demand.get(gid, 0.0) + qty

    # 6. market
    market.clear_market(s.goods, supply, demand, cfg)
    res.prices = {gid: g.price for gid, g in s.goods.items()}
    res.sector_output = supply

    # 7. procurement
    res.delivered, res.procurement_cost = _procure(s, s.government.defense_budget, w)

    # 8. man the force
    (
        res.operational_tokens,
        res.training_tokens,
        res.personnel_cost,
        res.manpower_operational,
        res.maintenance_load,
    ) = _man_the_force(s, pool, cfg, w)

    # 9. budget reconciliation
    civilian_left = s.government.civilian_budget - res.project_cost
    defense_left = s.government.defense_budget - res.procurement_cost - res.personnel_cost
    if civilian_left < 0:
        w.append(f"civilian budget overspent by {-civilian_left:,.0f}")
    if defense_left < 0:
        w.append(f"defense budget overspent by {-defense_left:,.0f}")
    s.government.treasury += civilian_left + defense_left
    if s.government.treasury < 0:
        s.government.debt += -s.government.treasury
        s.government.treasury = 0.0

    # 10. stability
    _standard_of_living(s, supply, demand)

    # 11. macro + advance year
    s.gdp = _gdp(s, supply)
    s.manpower.active_operational = res.manpower_operational
    s.manpower.active_training = sum(
        t * s.units[tid].men_per_token for tid, t in res.training_tokens.items()
    )
    s.year += 1
    # next year's inputs start fresh
    s.procurement_orders = []
    s.new_project_ids = []
    return res
