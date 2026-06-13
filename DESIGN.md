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
tests/            stdlib unittest
```

## The annual tick (`resolve.tick`)

Pure, deterministic, no RNG:

1. **Projects** — tick lead times; on completion apply adjudicated `StateDelta`s.
2. **Manpower pool** — sized from readiness (1 volunteers … 4 general mobilisation).
3. **Labour drain** — the call-up is pulled from *non-essential* sector labour
   (essential = food etc. are shielded → the economy↔manpower tradeoff).
4. **Production** — sector output = labour × productivity × efficiency; emits
   supply and input demand.
5. **Consumption** — pop strata buy their needs baskets → demand.
6. **Market** — clear prices (band-clamped; importable goods capped at import price).
7. **Procurement** — spend the defense budget; domestic gated by arms capacity,
   imports by money; deliver tokens to the stockpile.
8. **Man the force** — allocate men to owned equipment; equipment without men
   stays in **Training** (the readiness gate from the manpower policy).
9. **Budget** — reconcile civilian + defense envelopes into treasury / debt.
10. **Stability** — standard-of-living → loyalty → politically-weighted stability.
11. **Macro** — recompute output value; advance the year; clear per-turn inputs.

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

## Known gaps / roadmap

- **Currency calibration.** GDP is currently the value of production in *model
  price units* (~4.2M), not the headline $4.4bn. Mapping units → currency (a
  price-scale balancing pass) is a TODO; the structure is in place.
- **Full token catalogue & umpire prices.** Only a representative subset of the
  Y0 sheet's units is encoded; the full list + real domestic/import price
  estimates come next (likely via an importer for the existing `.xlsx`).
- **Three procurement channels** (Domestic / Japanese / Western imports) — V1
  uses a single generic import channel; split later.
- **Pops depth** — strata exist with needs/loyalty; income/wage formation and
  tax incidence are stubbed (budgets taken as given) and will be fleshed out.
- **Laws/policies** as first-class parameter modifiers (tariffs, franchise,
  land reform, mobilization) beyond the readiness lever.
- **Stockpiles & ammo** consumption, capital works (depots/airfields/forts),
  and a feedback path for tactical losses/territory.
- **Local web UI** for non-technical umpires: guided initial-state encoding +
  per-turn numeric decision entry over this engine.
