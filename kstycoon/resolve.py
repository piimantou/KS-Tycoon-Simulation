"""The annual financial-year tick.

``tick(state)`` is a pure function: it deep-copies the incoming state, applies
the ordered resolution below, and returns a :class:`TickResult` holding the new
state plus everything the handoff report needs. No randomness — campaigns are
fully reproducible.

Fast vs slow variables
  Within a period the *fast* variables — prices, production, incomes,
  consumption — are solved to a joint equilibrium (a fixed point), so the
  reported year is a settled state rather than a transient mid-swing. The *slow*
  stocks — population, treasury, debt, forex, pop wealth, capacity — evolve
  *between* periods.

Order of resolution
  1. advance projects (apply adjudicated effects on completion)
  2. size the manpower pool from readiness
  3. derive sector employment from pops; apply conscription as a *transient* draw
  4. fixed supply + intermediate demand
  5. solve the per-period equilibrium (prices <-> incomes <-> consumption)
  6. tax revenue -> spending envelopes
  7. procurement (domestic gated by arms capacity; imports gated by money + forex)
  8. man the force (equipment + men -> Operational vs Training)
  9. budget reconciliation + debt service
 10. forex reserve update
 11. standard of living -> loyalty -> stability
 12. household savings stock
 13. demographics (population grows from standard of living)
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
# Projects
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
    elif d.target == "sector_labour_share" and d.key in state.sectors:
        state.sectors[d.key].labour_share = op(state.sectors[d.key].labour_share)
    elif d.target == "sector_productivity" and d.key in state.sectors:
        state.sectors[d.key].productivity = op(state.sectors[d.key].productivity)
    elif d.target == "good_base_price" and d.key in state.goods:
        state.goods[d.key].base_price = op(state.goods[d.key].base_price)
    elif d.target == "stability":
        state.stability = op(state.stability)
    else:
        warnings.append(f"delta target '{d.target}/{d.key}' had no effect")


def _advance_projects(state: m.GameState, warnings: list[str]) -> float:
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


# --------------------------------------------------------------------------- #
# Manpower & labour
# --------------------------------------------------------------------------- #
def _manpower_pool(mp: m.Manpower) -> float:
    """Callable manpower by readiness level (cumulative tiers)."""
    base = mp.population * mp.volunteer_fraction
    if mp.readiness >= 3:
        base += mp.population * mp.conscription_i_fraction
    if mp.readiness >= 4:
        base = mp.population * (mp.volunteer_fraction + mp.conscription_ii_fraction)
    return base


def _effective_labour(
    state: m.GameState, pool: float, warnings: list[str]
) -> dict[str, float]:
    """Employment per sector this period = national labour force × labour_share,
    minus a **transient** conscription draw from non-essential sectors.

    The draw is *not* written back to the state — next period it is recomputed
    from a fresh labour force, so conscription no longer compounds and
    demobilisation returns workers automatically. Labour also grows with the
    population (which grows over time), so pops are no longer static.
    """
    lf = state.labour_force
    eff = {sid: lf * s.labour_share for sid, s in state.sectors.items()}

    nonessential = [sid for sid, s in state.sectors.items() if not s.essential]
    available = sum(eff[sid] for sid in nonessential)
    if available > 0:
        drain = min(pool, available)
        if pool > available:
            warnings.append(
                "manpower call-up exceeds non-essential labour; economy fully stripped"
            )
        factor = 1.0 - (drain / available)
        for sid in nonessential:
            eff[sid] *= factor
    return eff


def _sector_output(s: m.Sector, eff: dict[str, float]) -> float:
    return eff.get(s.id, 0.0) * s.productivity * s.efficiency


def _supply_inputs(
    state: m.GameState, eff: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
    """Supply and intermediate (input) demand — fixed within the period."""
    supply: dict[str, float] = {}
    input_demand: dict[str, float] = {}
    for s in state.sectors.values():
        out = _sector_output(s, eff)
        if s.output_good:
            supply[s.output_good] = supply.get(s.output_good, 0.0) + out
        for gid, qty in s.inputs_per_output.items():
            input_demand[gid] = input_demand.get(gid, 0.0) + out * qty
    return supply, input_demand


# --------------------------------------------------------------------------- #
# Incomes, consumption, equilibrium
# --------------------------------------------------------------------------- #
def _incomes(state: m.GameState, eff: dict[str, float]) -> tuple[float, float]:
    """Distribute each sector's value-added into wages (workers) and surplus
    (owners, or the treasury if state-owned). Sets pop.income; returns
    (state_enterprise_surplus, gdp_currency)."""
    scale = state.currency_scale
    for pop in state.pops.values():
        pop.income = 0.0
    state_surplus = 0.0
    gdp = 0.0
    for s in state.sectors.values():
        out = _sector_output(s, eff)
        if out <= 0:
            continue
        if s.output_good and s.output_good in state.goods:
            gross = out * state.goods[s.output_good].price
        else:
            gross = out  # services priced at 1 model unit/output
        input_cost = sum(
            out * qty * state.goods[gid].price
            for gid, qty in s.inputs_per_output.items()
            if gid in state.goods
        )
        va = max(0.0, gross - input_cost) * scale
        gdp += va
        wages = va * s.wage_share
        surplus = va - wages
        if s.worker_pop and s.worker_pop in state.pops:
            state.pops[s.worker_pop].income += wages
        else:
            surplus += wages
        if s.state_owned:
            state_surplus += surplus
        elif s.owner_pop and s.owner_pop in state.pops:
            state.pops[s.owner_pop].income += surplus
        else:
            state_surplus += surplus
    return state_surplus, gdp


def _basket_cost(pop: m.PopStratum, state: m.GameState) -> float:
    cost = 0.0
    for gid, per_cap in pop.needs_per_capita.items():
        g = state.goods.get(gid)
        if g:
            cost += per_cap * g.price
    return cost * state.currency_scale


def _affordability(pop: m.PopStratum, state: m.GameState) -> float:
    if pop.income <= 0 or pop.size <= 0:
        return 1.0
    basket = _basket_cost(pop, state)
    if basket <= 0:
        return 1.0
    disposable = (pop.income * (1.0 - state.government.income_tax_rate)) / pop.size
    return max(0.0, min(1.0, disposable / basket))


def _consumption(state: m.GameState) -> dict[str, float]:
    demand: dict[str, float] = {}
    for pop in state.pops.values():
        afford = _affordability(pop, state)
        for gid, per_cap in pop.needs_per_capita.items():
            demand[gid] = demand.get(gid, 0.0) + pop.size * per_cap * afford
    return demand


def _total_demand(state: m.GameState, input_demand: dict[str, float]) -> dict[str, float]:
    demand = dict(input_demand)
    for gid, q in _consumption(state).items():
        demand[gid] = demand.get(gid, 0.0) + q
    return demand


def _solve_equilibrium(
    state: m.GameState,
    eff: dict[str, float],
    supply: dict[str, float],
    input_demand: dict[str, float],
    cfg: Config,
) -> tuple[float, float, dict[str, float]]:
    """Iterate prices <-> incomes <-> consumption to a joint fixed point. Supply
    is fixed within the period; only demand, prices and incomes co-move."""
    state_surplus = gdp = 0.0
    for _ in range(cfg.equilibrium_iterations):
        state_surplus, gdp = _incomes(state, eff)
        demand = _total_demand(state, input_demand)
        if market.price_step(state.goods, supply, demand, cfg) < cfg.equilibrium_tol:
            break
    # final pass: incomes & demand consistent with the settled prices
    state_surplus, gdp = _incomes(state, eff)
    demand = _total_demand(state, input_demand)
    return state_surplus, gdp, demand


def _revenue_and_budget(state: m.GameState, state_surplus: float) -> None:
    g = state.government
    income_tax = sum(p.income for p in state.pops.values()) * g.income_tax_rate
    g.revenue = income_tax + state_surplus
    g.civilian_budget = g.revenue * g.civilian_share
    g.defense_budget = g.revenue * g.defense_share


# --------------------------------------------------------------------------- #
# Procurement & manpower gate
# --------------------------------------------------------------------------- #
def _procure(
    state: m.GameState, defense_budget: float, forex_cap: float, warnings: list[str]
) -> tuple[dict[str, dict], float, float]:
    """Spend the defense budget on orders. Domestic gated by arms capacity;
    imports gated by both money and the foreign-exchange cap. Returns
    (delivered, total_cost, import_spend)."""
    delivered: dict[str, dict] = {}
    cap_left = {cid: c.capacity for cid, c in state.arms.items()}
    spent = 0.0
    import_spent = 0.0

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
            by_money = int((defense_budget - spent) // price) if price > 0 else order.quantity
            qty = max(0, min(order.quantity, by_cap, by_money))
            if qty < order.quantity:
                lim = "arms capacity" if by_cap <= by_money else "budget"
                warnings.append(
                    f"{unit.name}: domestic order {order.quantity} -> {qty} (limited by {lim})"
                )
            cap_left[unit.category] = cap - qty
            rec["domestic"] += qty
        elif order.channel == "import":
            price = unit.import_price
            if price is None:
                warnings.append(f"{unit.name}: not available for import")
                continue
            by_money = int((defense_budget - spent) // price) if price > 0 else order.quantity
            by_forex = int((forex_cap - import_spent) // price) if price > 0 else order.quantity
            qty = max(0, min(order.quantity, by_money, by_forex))
            if qty < order.quantity:
                lim = "forex" if by_forex <= by_money else "budget"
                warnings.append(
                    f"{unit.name}: import order {order.quantity} -> {qty} (limited by {lim})"
                )
            rec["import"] += qty
            import_spent += qty * price
        else:
            warnings.append(f"{unit.name}: unknown channel '{order.channel}'")
            continue

        cost = qty * price
        rec["cost"] += cost
        spent += cost
        state.stockpile.tokens[order.unit_token_id] = (
            state.stockpile.tokens.get(order.unit_token_id, 0) + qty
        )
    return delivered, spent, import_spent


def _man_the_force(
    state: m.GameState, pool: float, cfg: Config, warnings: list[str]
) -> tuple[dict[str, int], dict[str, int], float, float, float]:
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

    mp = state.manpower
    volunteer_cap = mp.population * mp.volunteer_fraction
    volunteers = min(operational_men, volunteer_cap)
    conscripts = max(0.0, operational_men - volunteers)
    personnel_cost = (
        volunteers * mp.base_wage
        + conscripts * mp.base_wage * cfg.conscript_wage_factor
    )
    return operational, training, personnel_cost, operational_men, maint_load


# --------------------------------------------------------------------------- #
# Stocks: stability, household wealth, demographics
# --------------------------------------------------------------------------- #
def _standard_of_living(
    state: m.GameState, supply: dict[str, float], demand: dict[str, float]
) -> None:
    avail = {}
    for gid in set(list(supply) + list(demand)):
        d = demand.get(gid, 0.0)
        avail[gid] = 1.0 if d <= 0 else min(1.0, supply.get(gid, 0.0) / d)

    total_w = 0.0
    weighted = 0.0
    for pop in state.pops.values():
        afford = _affordability(pop, state)
        if not pop.needs_per_capita:
            availability = 1.0
        else:
            availability = sum(avail.get(g, 1.0) for g in pop.needs_per_capita) / len(
                pop.needs_per_capita
            )
        pop.sol = min(afford, availability)
        pop.loyalty = 0.7 * pop.loyalty + 0.3 * pop.sol
        w = max(pop.political_weight, 1e-9)
        weighted += pop.loyalty * w
        total_w += w
    if total_w > 0:
        state.stability = max(
            0.0, min(1.0, 0.5 * state.stability + 0.5 * (weighted / total_w))
        )


def _accumulate_wealth(state: m.GameState) -> None:
    """Close the household flow into a stock: pops spend up to their needs basket
    and save the rest (disposable income − consumption)."""
    tax = state.government.income_tax_rate
    for pop in state.pops.values():
        if pop.size <= 0:
            continue
        disposable_pc = pop.income * (1.0 - tax) / pop.size
        basket_pc = _basket_cost(pop, state)
        spending_pc = min(disposable_pc, basket_pc)
        pop.wealth += (disposable_pc - spending_pc) * pop.size


def _demographics(state: m.GameState) -> None:
    """Population grows from standard of living; strata grow proportionally
    (migration between strata is a later refinement)."""
    mp = state.manpower
    total = sum(p.size for p in state.pops.values())
    avg_sol = (
        sum(p.sol * p.size for p in state.pops.values()) / total if total > 0 else 0.5
    )
    rate = mp.base_growth_rate + mp.growth_sol_sensitivity * (avg_sol - 0.5)
    rate = max(-0.03, min(0.05, rate))
    factor = 1.0 + rate
    mp.population *= factor
    for pop in state.pops.values():
        pop.size *= factor


# --------------------------------------------------------------------------- #
def tick(state: m.GameState, cfg: Config | None = None) -> TickResult:
    cfg = cfg or Config()
    s = copy.deepcopy(state)
    res = TickResult(state=s)
    w = res.warnings
    g = s.government

    # 1. projects
    res.project_cost = _advance_projects(s, w)

    # 2. manpower pool
    pool = _manpower_pool(s.manpower)
    res.manpower_available = pool

    # 3. employment (pops -> labour, transient conscription)
    eff = _effective_labour(s, pool, w)

    # 4. fixed supply + intermediate demand
    supply, input_demand = _supply_inputs(s, eff)
    res.sector_output = supply

    # 5. per-period equilibrium (fast variables)
    state_surplus, s.gdp, demand = _solve_equilibrium(s, eff, supply, input_demand, cfg)
    res.prices = {gid: gd.price for gid, gd in s.goods.items()}

    # 6. revenue -> spending envelopes
    _revenue_and_budget(s, state_surplus)

    # 7. procurement (imports gated by money + forex available this year)
    forex_available = g.forex_reserve + g.export_earnings
    res.delivered, res.procurement_cost, import_spend = _procure(
        s, g.defense_budget, forex_available, w
    )

    # 8. man the force
    (
        res.operational_tokens,
        res.training_tokens,
        res.personnel_cost,
        res.manpower_operational,
        res.maintenance_load,
    ) = _man_the_force(s, pool, cfg, w)

    # 9. budget reconciliation + debt service
    interest = g.interest_rate * g.debt
    civilian_left = g.civilian_budget - res.project_cost
    defense_left = g.defense_budget - res.procurement_cost - res.personnel_cost
    if civilian_left < 0:
        w.append(f"civilian budget overspent by {-civilian_left:,.0f}")
    if defense_left < 0:
        w.append(f"defense budget overspent by {-defense_left:,.0f}")
    g.treasury += civilian_left + defense_left - interest
    if g.treasury < 0:
        g.debt += -g.treasury
        g.treasury = 0.0
    if g.credit_limit is not None and g.debt > g.credit_limit:
        w.append(f"debt ${g.debt:,.0f} exceeds credit limit ${g.credit_limit:,.0f}")

    # 10. forex reserve update (procurement imports drain it; exports replenish)
    g.forex_reserve = forex_available - import_spend
    if g.forex_reserve < 0:
        w.append("balance-of-payments deficit: foreign-exchange reserve exhausted")

    # 11. stability
    _standard_of_living(s, supply, demand)

    # 12. household savings stock
    _accumulate_wealth(s)

    # 13. demographics (uses this year's SoL)
    _demographics(s)

    # 14. macro carry + advance year
    s.manpower.active_operational = res.manpower_operational
    s.manpower.active_training = sum(
        t * s.units[tid].men_per_token for tid, t in res.training_tokens.items()
    )
    s.year += 1
    s.procurement_orders = []
    s.new_project_ids = []
    return res
