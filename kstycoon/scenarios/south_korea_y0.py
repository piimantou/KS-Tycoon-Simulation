"""Republic of Korea, 1924 (Year 0) starting scenario.

Hand-built from the umpire-provided ``South_Korea_Y0.xlsx`` and the player's
*Preliminary Report of the Ministry of Economy*. This is the engine's first
validation fixture: a "pre-modern" economy, near-zero domestic arms capacity
(so procurement is almost entirely imports at Y0), and the manpower tiers the
umpires specified.

Numbers that should reproduce the source material:
  * population 11,560,000; labour participation 42%
  * GDP per capita ≈ $381  (4.40e9 / 11.56e6)
  * Volunteers 1% (115,600) / Conscription I 10% (1,156,000) /
    Conscription II 19% (2,196,400)

Prices on military tokens are placeholders pending the umpires' real
estimates from the Y0 sheet (those cells were left as "???").
"""

from __future__ import annotations

from .. import model as m

POPULATION = 11_560_000
LABOUR_PARTICIPATION = 0.42
LABOUR_FORCE = POPULATION * LABOUR_PARTICIPATION  # 4,855,200


def _goods() -> dict[str, m.Good]:
    g = [
        m.Good("rice", "Rice", 1.0, 1.0, "food"),
        m.Good("fish", "Fish", 1.2, 1.2, "food"),
        m.Good("textiles", "Textiles", 2.0, 2.0, "consumer"),
        # import-dependent inputs (coal/steel/iron all scarce per the report)
        m.Good("coal", "Coal", 5.0, 5.0, "utility", importable=True, import_price=6.0),
        m.Good("steel", "Steel", 20.0, 20.0, "military_input",
               importable=True, import_price=24.0),
        m.Good("machinery", "Machinery", 50.0, 50.0, "input",
               importable=True, import_price=60.0),
    ]
    return {x.id: x for x in g}


def _sectors() -> dict[str, m.Sector]:
    # labour_share = fraction of the national labour force employed in the sector
    # (shares sum to ~0.92; the remainder is unemployed/unmodelled).
    s = [
        # Agriculture: ~70% Japanese-owned land -> low wage share, surplus to elite.
        m.Sector("agriculture", "Agriculture", "rice",
                 labour_share=0.71, productivity=0.70, essential=True,
                 worker_pop="rural_lower", owner_pop="upper", wage_share=0.50),
        m.Sector("fishing", "Coastal Fishing", "fish",
                 labour_share=0.02, productivity=2.5, essential=True,
                 worker_pop="rural_lower", owner_pop="middle", wage_share=0.60),
        m.Sector("extraction", "Extraction (coal)", "coal",
                 labour_share=0.02, productivity=1.5,
                 worker_pop="urban_lower", owner_pop="upper", wage_share=0.55),
        m.Sector("light_industry", "Light Industry (textiles)", "textiles",
                 labour_share=0.05, productivity=3.0,
                 inputs_per_output={"machinery": 0.02},
                 worker_pop="urban_lower", owner_pop="upper", wage_share=0.60),
        m.Sector("heavy_industry", "Heavy Industry (steel)", "steel",
                 labour_share=0.01, productivity=0.5,
                 inputs_per_output={"coal": 1.5},
                 worker_pop="urban_lower", owner_pop="upper", wage_share=0.60),
        m.Sector("services", "Services", None,
                 labour_share=0.11, productivity=1.0,
                 worker_pop="middle", owner_pop="middle", wage_share=0.70),
    ]
    return {x.id: x for x in s}


def _arms() -> dict[str, m.ArmsCapacity]:
    # Pre-modern: almost nothing. A token slipway exists but no live line yet.
    a = [
        m.ArmsCapacity("small_arms", capacity=20.0, inputs_per_token={"steel": 2.0}),
        m.ArmsCapacity("artillery", capacity=0.0, inputs_per_token={"steel": 8.0}),
        m.ArmsCapacity("armor", capacity=0.0, inputs_per_token={"steel": 15.0}),
        m.ArmsCapacity("aircraft", capacity=0.0),
        m.ArmsCapacity("anti_tank", capacity=0.0, inputs_per_token={"steel": 6.0}),
        m.ArmsCapacity("support", capacity=0.0),
        m.ArmsCapacity("naval", capacity=0.0),
        m.ArmsCapacity("ammo", capacity=0.0),
    ]
    return {x.category: x for x in a}


def _units() -> dict[str, m.UnitToken]:
    # Representative subset of the Y0 token catalogue. Prices are placeholders.
    u = [
        m.UnitToken("rifles", "Rifle Platoon", "small_arms",
                    men_per_token=30, maintenance_tokens=0.0,
                    domestic_price=9_000, import_price=12_000, ammo_type="bullets"),
        m.UnitToken("mmg", "MMG Platoon", "small_arms",
                    men_per_token=10, maintenance_tokens=0.0,
                    domestic_price=20_000, import_price=26_000, ammo_type="bullets"),
        m.UnitToken("light_mortar", "Light Mortar", "artillery",
                    men_per_token=30, maintenance_tokens=0.0,
                    domestic_price=None, import_price=25_000, ammo_type="light_mortar"),
        m.UnitToken("light_field_gun", "Light Field Gun (Light Tube)", "artillery",
                    men_per_token=30, maintenance_tokens=0.0,
                    domestic_price=None, import_price=40_000, ammo_type="light_tube"),
        m.UnitToken("light_tank", "Light Tank Troop", "armor",
                    men_per_token=30, maintenance_tokens=0.25,
                    domestic_price=None, import_price=60_000, ammo_type="at_tube"),
        m.UnitToken("biplane_fighter", "Biplane Fighter (x4)", "aircraft",
                    men_per_token=30, maintenance_tokens=1.0,
                    domestic_price=None, import_price=80_000, ammo_type="light_aa"),
        m.UnitToken("light_at", "Light Anti-Tank", "anti_tank",
                    men_per_token=30, maintenance_tokens=0.0,
                    domestic_price=None, import_price=30_000, ammo_type="light_at"),
        m.UnitToken("truck", "Truck Company", "support",
                    men_per_token=30, maintenance_tokens=0.0,
                    domestic_price=None, import_price=8_000, ammo_type="fuel"),
    ]
    return {x.id: x for x in u}


def _pops() -> dict[str, m.PopStratum]:
    p = [
        m.PopStratum("rural_lower", "Rural / Peasants", "lower", size=8_000_000,
                     needs_per_capita={"rice": 0.20, "fish": 0.02},
                     political_weight=0.2, loyalty=0.5),
        m.PopStratum("urban_lower", "Urban Workers", "lower", size=2_000_000,
                     needs_per_capita={"rice": 0.20, "fish": 0.02, "textiles": 0.05},
                     political_weight=0.4, loyalty=0.5),
        m.PopStratum("middle", "Middle / Professionals", "middle", size=1_200_000,
                     needs_per_capita={"rice": 0.20, "textiles": 0.20, "machinery": 0.005},
                     political_weight=0.7, loyalty=0.55),
        m.PopStratum("upper", "Capitalists / Aristocrats", "upper", size=360_000,
                     needs_per_capita={"rice": 0.20, "textiles": 0.50},
                     political_weight=1.0, loyalty=0.6),
    ]
    return {x.id: x for x in p}


def _projects() -> dict[str, m.Project]:
    p = [
        m.Project(
            "bosco", "Steel Industrial Development (BOSCO)", "Industry",
            allocation=35_000_000, lead_time_years=3, remaining_years=3,
            effects=[
                m.StateDelta("sector_productivity", "heavy_industry", "mul", 4.0),
                m.StateDelta("arms_capacity", "small_arms", "add", 60.0),
            ],
            note="State-owned steel mill at Busan on foreign inputs; foreign equity <=40%.",
        ),
        m.Project(
            "shipbuilding", "Shipbuilding Formalisation", "Industry",
            allocation=15_000_000, lead_time_years=2, remaining_years=2,
            effects=[m.StateDelta("arms_capacity", "naval", "add", 0.5)],
            note="Seed-fund local shipbuilders into a formal yard.",
        ),
        m.Project(
            "dams", "Dam Construction (Hydroelectric)", "Energy",
            allocation=20_000_000, lead_time_years=3, remaining_years=3,
            effects=[m.StateDelta("sector_efficiency", "light_industry", "mul", 1.25)],
            note="Expand hydro power; lifts industrial efficiency.",
        ),
    ]
    return {x.id: x for x in p}


def build() -> m.GameState:
    state = m.GameState(
        year=1924,
        nation="Republic of Korea",
        goods=_goods(),
        sectors=_sectors(),
        arms=_arms(),
        units=_units(),
        pops=_pops(),
        projects=_projects(),
        manpower=m.Manpower(
            population=POPULATION,
            labour_participation=LABOUR_PARTICIPATION,
            volunteer_fraction=0.01,
            conscription_i_fraction=0.10,
            conscription_ii_fraction=0.19,
            readiness=1,
            base_wage=300.0,
            base_growth_rate=0.012,        # ~1.2%/yr at neutral SoL (1920s Korea)
            growth_sol_sensitivity=0.03,
        ),
        government=m.Government(
            treasury=0.0,
            debt=0.0,
            # Budgets are now *computed* from tax revenue. These levers are
            # calibrated so Y0 lands near the source figures: ~$200M civilian
            # ($200M departments + reserve) and ~$220M defense.
            income_tax_rate=0.10,
            tariff_rate=0.0,
            civilian_share=0.455,   # -> ~$200M civilian (departments + reserve)
            defense_share=0.500,    # -> ~$220M defense (procurement sheet)
            # Stocks & financing. Heavy reliance on (costly) Japanese credit;
            # exports (rice/fish) earn the forex that pays for arms imports.
            interest_rate=0.05,
            credit_limit=2_000_000_000,
            forex_reserve=40_000_000,
            export_earnings=30_000_000,
        ),
        # Calibrated so the settled-equilibrium value-added ≈ the headline GDP
        # of $4.4bn ($381/capita) in the opening year.
        currency_scale=1423.0,
        gdp=4_400_000_000,
        stability=0.5,
    )

    # --- example Year-0 directives the umpire keys in ---
    state.new_project_ids = ["bosco", "shipbuilding", "dams"]
    state.procurement_orders = [
        # domestic small arms within the 20-token capacity, rest imported
        m.ProcurementOrder("rifles", "domestic", 20),
        m.ProcurementOrder("rifles", "import", 100),
        m.ProcurementOrder("light_field_gun", "import", 20),
        m.ProcurementOrder("light_at", "import", 10),
        m.ProcurementOrder("truck", "import", 15),
    ]
    return state
