"""Domain model for the KS-Tycoon economic engine.

These are plain dataclasses with no behaviour — the resolver in
:mod:`kstycoon.resolve` is the only thing that mutates them. Keeping the model
inert makes the whole state trivially serialisable (see
:mod:`kstycoon.serialize`) and the simulation fully reproducible.

Altitude of the model (decided with the umpire):
  * economy = a handful of **sectors** over a **pop/strata** substrate with a
    **floating market**; bespoke projects are *adjudicated* by the umpire into
    quantified :class:`StateDelta` effects.
  * procurement = **token-based**, two channels (Domestic / Import) for V1.
  * manpower = one Active-Forces pool, conscription tiers × readiness, with a
    Training -> Operational gate driven by equipment + upkeep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------- #
# Economy: goods, sectors, population
# --------------------------------------------------------------------------- #
@dataclass
class Good:
    """A tradeable good carrying a base price and a current (floating) price."""

    id: str
    name: str
    base_price: float
    price: float
    category: str  # "food" | "input" | "consumer" | "military_input" | "utility"
    importable: bool = False          # can be bought on the import market
    import_price: Optional[float] = None  # exogenous world price (umpire-set)


@dataclass
class Sector:
    """A production sector. Employment is derived each period from the national
    labour force × ``labour_share`` (so it grows with population and shrinks
    transiently under conscription); output = employment × productivity ×
    efficiency, consuming input goods per unit of output."""

    id: str
    name: str
    output_good: Optional[str]                 # good id produced (None = pure service)
    labour_share: float                        # fraction of the national labour force
    productivity: float                        # output units / worker / year (at eff=1)
    efficiency: float = 1.0                    # capital/power/skill multiplier
    inputs_per_output: dict[str, float] = field(default_factory=dict)
    essential: bool = False                    # labour shielded from conscription
    state_owned: bool = False                  # surplus accrues to the state, not owners
    # income formation: value-added splits into wages (to workers) and surplus
    # (to owners, or to the treasury if state-owned).
    worker_pop: Optional[str] = None           # stratum that supplies labour & earns wages
    owner_pop: Optional[str] = None             # stratum that receives the surplus
    wage_share: float = 0.6                    # fraction of value-added paid as wages


@dataclass
class PopStratum:
    """A class of pops (never individuals). Drives consumption demand, supplies
    labour, and carries political weight + loyalty for the stability layer."""

    id: str
    name: str
    strata: str                                # "lower" | "middle" | "upper"
    size: float
    needs_per_capita: dict[str, float] = field(default_factory=dict)  # good -> qty/yr
    political_weight: float = 0.0
    loyalty: float = 0.5                       # 0..1, updated from standard of living
    income: float = 0.0                        # gross annual income (currency), computed
    sol: float = 1.0                           # standard of living 0..1, computed
    wealth: float = 0.0                        # accumulated savings stock (currency)


# --------------------------------------------------------------------------- #
# Military: domestic arms capacity, unit tokens
# --------------------------------------------------------------------------- #
@dataclass
class ArmsCapacity:
    """Domestic military production capacity for one category, in tokens/year.
    This is the lever the *economy* layer grows (via projects/subsidies) and the
    *procurement* layer spends."""

    category: str
    capacity: float                            # tokens producible per year
    inputs_per_token: dict[str, float] = field(default_factory=dict)


@dataclass
class UnitToken:
    """A procurable unit token — the unit of account shared with the tactical
    layer. A token abstracts e.g. ~30 men or ~3 guns/vehicles."""

    id: str
    name: str
    category: str                              # maps to ArmsCapacity.category
    men_per_token: float
    maintenance_tokens: float                  # upkeep load
    domestic_price: Optional[float] = None     # None = not domestically producible
    import_price: Optional[float] = None       # None = not importable
    ammo_type: Optional[str] = None


# --------------------------------------------------------------------------- #
# Projects: adjudicated, time-delayed effects on state
# --------------------------------------------------------------------------- #
@dataclass
class StateDelta:
    """A quantified, umpire-adjudicated effect on the economic state, applied
    when a project completes.

    target/key/op/value, e.g. ("arms_capacity", "small_arms", "add", 200) or
    ("sector_efficiency", "heavy_industry", "mul", 1.25).
    """

    target: str
    key: str
    op: str                                    # "add" | "mul" | "set"
    value: float


@dataclass
class Project:
    """A named development project. The umpire translates the player's prose
    directive into ``effects``; the engine applies them after ``lead_time``."""

    id: str
    name: str
    department: str
    allocation: float
    lead_time_years: int
    remaining_years: int
    effects: list[StateDelta] = field(default_factory=list)
    note: str = ""


@dataclass
class ConstructionWork:
    """Capital works (depots, airfields, fortifications) handed to the tactical
    layer; tracked separately from the budget."""

    id: str
    name: str
    quantity: int
    maintenance_tokens: float = 0.0


# --------------------------------------------------------------------------- #
# Manpower & government
# --------------------------------------------------------------------------- #
@dataclass
class Manpower:
    """The single Active-Forces manpower model."""

    population: float
    labour_participation: float                # fraction of pop in the labour force
    volunteer_fraction: float                  # of population
    conscription_i_fraction: float             # of population (partial mobilisation)
    conscription_ii_fraction: float            # of population (general mobilisation)
    readiness: int = 1                         # 1..4
    base_wage: float = 0.0                     # annual wage per operational soldier
    # --- demographics (population is no longer static) ---
    base_growth_rate: float = 0.005            # annual population growth at neutral SoL
    growth_sol_sensitivity: float = 0.04       # extra growth per unit of SoL above 0.5
    # carried accounting (recomputed each tick):
    active_training: float = 0.0
    active_operational: float = 0.0


@dataclass
class Government:
    treasury: float
    debt: float = 0.0
    # --- tax policy (player levers) ---
    income_tax_rate: float = 0.0               # flat tax on pop income
    tariff_rate: float = 0.0                   # surcharge on imported-good consumption
    # --- how computed revenue is split into spending envelopes ---
    civilian_share: float = 0.5                # of revenue -> development
    defense_share: float = 0.5                 # of revenue -> procurement + upkeep
    # --- stocks & financing (stock-flow consistency) ---
    interest_rate: float = 0.0                 # annual interest charged on debt
    credit_limit: Optional[float] = None       # max debt before a financing warning
    forex_reserve: float = 0.0                 # foreign exchange stock for imports
    export_earnings: float = 0.0               # annual forex inflow (exports)
    # --- computed each tick ---
    revenue: float = 0.0
    civilian_budget: float = 0.0               # ministries / development envelope
    defense_budget: float = 0.0                # procurement + upkeep envelope


@dataclass
class ProcurementOrder:
    unit_token_id: str
    channel: str                               # "domestic" | "import"
    quantity: int


@dataclass
class Stockpile:
    tokens: dict[str, int] = field(default_factory=dict)   # unit_token_id -> owned
    works: dict[str, int] = field(default_factory=dict)    # work id -> built


# --------------------------------------------------------------------------- #
# Whole-game state
# --------------------------------------------------------------------------- #
@dataclass
class GameState:
    year: int
    nation: str
    goods: dict[str, Good] = field(default_factory=dict)
    sectors: dict[str, Sector] = field(default_factory=dict)
    arms: dict[str, ArmsCapacity] = field(default_factory=dict)
    units: dict[str, UnitToken] = field(default_factory=dict)
    pops: dict[str, PopStratum] = field(default_factory=dict)
    works: dict[str, ConstructionWork] = field(default_factory=dict)
    projects: dict[str, Project] = field(default_factory=dict)
    manpower: Optional[Manpower] = None
    government: Optional[Government] = None
    stockpile: Stockpile = field(default_factory=Stockpile)

    # ---- per-turn player inputs (set by the umpire each year) ----
    procurement_orders: list[ProcurementOrder] = field(default_factory=list)
    new_project_ids: list[str] = field(default_factory=list)   # projects started this year

    # ---- macro snapshot (recomputed each tick) ----
    gdp: float = 0.0
    stability: float = 0.5
    # Converts model output-value (price units) to headline currency. A light
    # calibration so wages/taxes/budget are denominated in the scenario's $.
    currency_scale: float = 1.0

    @property
    def labour_force(self) -> float:
        return self.manpower.population * self.manpower.labour_participation
