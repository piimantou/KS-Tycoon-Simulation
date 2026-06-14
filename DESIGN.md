# KS-Tycoon — Design

A deterministic engine that runs the **civilian economy → procurement →
manpower** layer of a Discord-mediated, umpire-run Kriegsspiel. It is *not* a
Discord bot and not the tactical game. Its single deliverable is a **handoff
report**: a roster of operational unit tokens (men + equipment + upkeep) plus
capital works, handed to the (separate) tactical layer.

## Inspiration & altitude

Borrowed from Victoria 3 / EU5: **goods + a floating market**, **pops by
class**, **production capacity with lead times**, and **laws as parameter
modifiers**. But at ~5% of their weight: a human umpire resolves one financial
year at a time, so the model takes the *shape* of those systems, not their
continuous general-equilibrium solver.

## Decisions locked with the umpire

| Decision | Choice |
|---|---|
| Scope (V1) | One nation, annual financial-year tick, domestic economy first |
| Pops | Simulated by **class/strata** (Vic3 taxonomy as reference), not individuals |
| Market | **Floating** prices (supply/demand within a band) + import price caps |
| Supply chain | **Shallow** — a few inputs (coal, steel, machinery) feed end-items |
| Economy model | **Sector-based**; bespoke projects **adjudicated by the umpire** into quantified deltas, engine simulates downstream |
| Procurement | **Token-based**; **Domestic + one Import channel** for V1 |
| Imports | Exogenous, umpire-set prices (no foreign agency yet) |
| Manpower | One **Active-Forces pool**, conscription tiers × readiness, Training→Operational gate |
| Stack | **Python** engine; **local web app** UI (later) |
| Build order | Engine + South Korea Y0 fixture first; UI after the model is sound |

The guiding split: **engine = deterministic ledger/simulator; umpire = judgment
on bespoke project effects.** This is faithful to free-Kriegsspiel and tractable.

## How players interact (decision altitude)

Grounded in the *Ministry of Economy* report and the `South_Korea_Y0.xlsx`
sheet the umpires provided. Players do **not** micromanage buildings. They issue
**ministry directives**: split a budget across departments, fund **named
projects with objectives** ("$35M → establish BOSCO state steel company"), set
**policies** (conscription terms, mobilization readiness, tariffs, land reform),
and place **procurement orders** by token and channel. The umpire translates
prose directives into quantified `StateDelta` effects; the engine does the rest.

## Architecture

```
        ministry directives + policies (player input, via the umpire)
                              │
   ┌──────────────────────────────────────────────────────────┐
   │ ECONOMY  — sectors over a pop/strata substrate + market    │
   │ outputs: arms-production capacity, resources, labour pool, │
   │ revenue, stability inputs                                  │
   └───────────────┬───────────────────────┬────────────────────┘
            (capacity, $)            (labour pool, exemptions)
                   ▼                         ▼
        ┌────────────────────┐    ┌────────────────────────┐
        │ PROCUREMENT         │    │ MANPOWER                │
        │ $ → tokens (Dom/Imp)│    │ pool × readiness;        │
        │ gated by capacity   │    │ Training→Operational gate│
        └─────────┬───────────┘    └───────────┬─────────────┘
                  └────────────┬────────────────┘
                               ▼
        HANDOFF: operational tokens + capital works → tactical Kriegsspiel
```

### Code layout
```
kstycoon/
  model.py        inert dataclasses (the whole game state)
  config.py       tunable constants (the balancing dials)
  market.py       floating-price tâtonnement
  resolve.py      the annual tick (pure: state -> TickResult)
  report.py       Markdown handoff report
  serialize.py    JSON load/save (generic, hint-driven)
  scenarios/
    south_korea_y0.py   the 1924 RoK validation fixture
  cli.py          thin driver: new / tick / report
  web.py          first-pass local web UI (stdlib http.server + embedded SPA)
tests/            stdlib unittest
```

### Web UI (first pass)
`python -m kstycoon.web` serves a single-page console at `127.0.0.1:8000`. It is
dependency-free: a stdlib HTTP server exposes `GET /api/state` and
`POST /api/tick` (decisions in, report + new state out), and the embedded
vanilla-JS page lets the umpire set tax/budget-split/readiness, fund projects,
queue procurement orders, and run the year. State persists to a JSON file.
Roadmap: initial-state *editing* (not just per-turn directives), multi-nation
selection, and richer charts.

## The annual tick (`resolve.tick`)

Pure, deterministic, no RNG:

**Fast vs slow variables.** Within a period the *fast* variables (prices,
production, incomes, consumption) are solved to a **joint equilibrium** — a fixed
point reached by iterating incomes↔consumption↔prices to convergence — so the
reported year is a settled state, not a transient mid-swing. The *slow* stocks
(population, treasury, debt, forex, pop wealth, capacity) evolve **between**
periods.

1. **Projects** — tick lead times; on completion apply adjudicated `StateDelta`s.
2. **Manpower pool** — sized from readiness (1 volunteers … 4 general mobilisation).
3. **Employment** — derived from pops: `national labour force × labour_share`,
   minus a **transient** conscription draw from non-essential sectors (shielding
   essentials). The draw is *not* persisted, so it no longer compounds and
   demobilisation returns workers; employment grows with population.
4. **Supply** — sector output = employment × productivity × efficiency (fixed
   within the period); emits supply + intermediate demand.
5. **Equilibrium solve** — iterate incomes (value-added → wages/surplus →
   pop income) ↔ consumption (affordability = disposable income vs basket cost)
   ↔ prices (band-clamped; importable goods capped at import price) to a fixed
   point.
6. **Revenue → budgets** — income tax + state-enterprise surplus → civilian /
   defense envelopes.
7. **Procurement** — domestic gated by arms capacity; imports gated by **money
   and the foreign-exchange reserve**; deliver tokens to the stockpile.
8. **Man the force** — allocate men to owned equipment; equipment without men
   stays in **Training**.
9. **Budget + debt service** — reconcile envelopes; charge interest on debt;
   deficits accrue to debt (vs a credit limit).
10. **Forex** — exports replenish the reserve; procurement imports drain it.
11. **Stability** — standard-of-living → loyalty → politically-weighted stability.
12. **Wealth** — pops save (disposable income − consumption) into a wealth stock.
13. **Demographics** — population (and strata) grow from standard of living.

## Validation fixture: South Korea, 1924

Reproduces the source figures: population 11.56M, labour participation 42%,
manpower tiers 1% / 10% / 19% (115,600 / 1,156,000 / 2,196,400). The economy is
"pre-modern" with near-zero domestic arms capacity, so Y0 procurement is almost
entirely imports — exactly the intended dynamic. Run it:

```
python -m kstycoon.cli new /tmp/sk.json
python -m kstycoon.cli report /tmp/sk.json
python -m unittest discover -s tests
```

## Roadmap

**Workstream A — make the economy behave (done).** Transient conscription
(no more decay), employment derived from pops, per-period equilibrium solve,
SoL-driven demographics, and stock-flow stocks (pop wealth, debt + interest,
forex reserve). GDP/cap calibrated to ~$381 in the opening year.

**Workstream B — make it richer (next).**
- **Capacity + TFP per sector**: expansion CapEx (grows capacity, lead time) vs
  R&D (grows TFP); discrete tech bumps may step input bundles.
- **More goods/sectors** and an inter-sector input matrix (deeper supply chain).
- **CapEx vs OpEx**: bill recurring upkeep in money (maintenance tokens × cost,
  sector/admin overhead) — currently maintenance is tracked only as tokens.
- **Full token catalogue & real prices** (import the Y0 `.xlsx`); split imports
  into Japanese / Western channels.

**Workstream C — player-input layer.** Driven by the umpire's forthcoming design
doc (decision vocabulary, cadence, mechanical-vs-adjudicated split).

**Known simplifications still open.**
- Civilian intermediate imports (coal/steel/machinery) cap prices but are **not**
  yet billed against forex — only *procurement* imports are. Full balance-of-
  payments needs a trade-price calibration pass (with B).
- Demographics grow strata proportionally; **migration/urbanisation** between
  strata is a later refinement.
- Tax is flat; **progressive/per-strata incidence** is future.
- **Laws/policies** as first-class modifiers (tariffs, franchise, land reform)
  beyond the readiness and tax levers.
- **Ammo consumption**, capital works (depots/airfields/forts), and a feedback
  path for tactical losses/territory.
