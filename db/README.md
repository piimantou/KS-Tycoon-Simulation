# Umpire's database

The Economic Tables workbook, rebuilt as plain-text tables plus a small engine
that fills in the rows a spreadsheet would compute. Git is the history: one
commit per tick shows exactly which numbers moved.

```
db/
  ref/                      reference tables, shared by every game
    classes.csv               L1..L5
    goods.csv                 goods; `capital` marks K1/K2/K3
    consumption_weights.csv   Guide III.C table
    demand_group_goods.csv    which goods satisfy each demand group
    recipes.csv               the I-O Tables sheet, one row per building level
    params.toml               design dials (bundle scale, upgrade mode, ...)
  games/<game>/
    game.toml                 start tick, seed, promotion months, param overrides
    setup/                    opening stocks (population, buildings)
    exogenous/                what the umpire enters      <- the only thing edited in play
    ledger/                   what the engine computes    <- never edited by hand
    REPORT.md                 headline indicators, regenerated every tick
```

## Running a turn

1. Edit the three files in `games/<game>/exogenous/`.
2. Resolve the tick:
   ```bash
   python -m ksdb advance example
   ```
3. Read `REPORT.md`, commit.

Other commands: `check` (broken references and unfilled data), `replay`
(recompute the whole ledger from `setup/`), `report`, `new NAME`, and `site`
(build the browsable page into `_site/`).

Every push that touches `db/` or `ksdb/` redeploys that page to GitHub Pages:
all games, any tick, with the exogenous rows in force alongside the results.

`advance` only ever appends. Changing a past input, a recipe, or a parameter
does not touch resolved ticks until you run `replay`, and then `git diff` shows
what the retcon changed.

Without a local Python: edit the CSVs in GitHub's web editor, then run the
**Umpire database** workflow from the Actions tab; it resolves the tick and
commits the result.

## Exogenous inputs

**`population.csv`** and **`goods.csv`** hold *settings*: a row applies from
its `tick` until another row replaces it. Fill in `until` to make it a shock
that lapses after that tick. An active shock beats any open-ended row;
otherwise the most recent row wins.

| file | variable | scope | meaning |
|---|---|---|---|
| population | `births`, `deaths`, `migration` | class (or `*`) | people per tick, entered as counts |
| population | `promotion_rate` | class promoted *from* | chance each member moves up on a promotion month |
| population | `dependency` | class (or `*`) | dependents per working-age member |
| goods | `foreign_price` | good | the only price in the system so far |
| goods | `output_modifier` | good or building | multiplies output (harvests, strikes, sabotage) |

**`buildings.csv`** holds *events*, applied once on their tick:
`variable` is `size` (units of the building ordered, negative to remove) or a
capital code `K1`/`K2`/`K3` (capital goods added to that owner's pool).
`owner` is who holds the result; `source` is free text for where it came from
(`government_investment`, `foreign_investment`, `grant`, ...).

## What a tick does

Order matters, so it is fixed:

1. **Population.** On promotion months each class rolls
   Binomial(stock, rate) for promotions, drawn from last tick's stock as in the
   workbook. Births, deaths and migration are then added as entered. The dice
   are seeded from `seed`, the tick and the purpose, so a replay reproduces
   every roll; change `seed` to re-roll.
2. **Orders.** Capital pools wear by `capital_depreciation`; this tick's
   building events are booked. Capital added is demand on that capital good's
   market this tick.
3. **Labour.** Jobs come from whatever stood at the start of the tick. Each
   class fills its own jobs; surplus then takes vacancies in lower classes.
4. **Production.** Leontief per building level, scaled by the fill ratio of
   its scarcest labour class and by output modifiers. Inputs are *not* rationed:
   a shortfall shows up as a negative balance.
5. **Construction.** See below. What gets built starts working next tick.
6. **Consumption.** Bundle = stock × weight × (1 + dependency) × `bundle_scale`,
   the workbook formula. Size is fixed; price only sets what it costs.
7. **Goods markets.** Supply, demand by use (intermediate, household,
   investment), balance, and balance × price.

### Capital, levels and construction

A building entry is keyed by `(building, owner)` and carries a `size` in units
and a pool of each capital good. A recipe's `K1..K3` are the capital one unit
must hold to run at that level, so the pool decides the level mix. Capital is
spent bottom-up: every unit reaches level *n* before any reaches *n*+1.

`upgrade_mode` sets the grain, over the same state:

| mode | 5 units, 2,500 K1, level II needs 1,000/unit |
|---|---|
| `continuous` | 2.5 units at I, 2.5 at II |
| `unit` | 3 at I, 2 at II; 500 K1 waits in the pool |
| `building` | 5 at I until the pool reaches 5,000, then all 5 at II |

The gap between the level mix capital allows and what is built is the
**construction works** outstanding. A recipe's `construction` column is the
construction units needed to bring one unit up to that level (level 1 = build
it new). Each tick, the `Construction` good produced that tick is the capacity;
works are served by `construction_priority`, then pro rata, and the rest waits.
In the lumpy modes, construction received is banked until a whole unit (or
building) is paid for. Blank `construction` = free and immediate, which is the
state of the data today.

## Ported, inferred, placeholder

| | status |
|---|---|
| classes, consumption weights, dependency 0.5, promotion rates, 100 births/tick, 10,000 L1 | ported from the Guide and workbook |
| `recipes.csv` | ported 1:1; 219 rows, of which Rural Production L1 and Grain Farm L1-4 have figures |
| `construction` column, `Construction` good | added for the construction market; costs blank |
| `demand_group_goods.csv` | inferred (Food←Grain, Clothing←Cloth, Heating←Wood, Leisure←Services); Household and Intoxicants unmapped |
| example game: prices, 2 Rural Production, the Grain Farm events, the drought | placeholders to make the example move |

Run `python -m ksdb check example` for the current list of unfilled data.

## Assumptions the engine makes

These were needed to get from the tables to numbers and are not in the Guide.
Each is one parameter or one short block in `ksdb/engine.py`.

- **Stocks are working-age people.** Dependents exist only through the
  dependency ratio, as in the Consumption sheet; "births" are entrants to L1.
- **Promotions roll in May and November** (Guide III.B). The workbook rolls
  monthly; set `promotion_months` to all twelve to match it.
- **Recipe K figures are cumulative** per level, not increments.
- **Labour downfill**, and a building's throughput follows its scarcest class.
- **No rationing of goods.** Production never stalls for want of inputs and
  households always get their bundle; imbalances are reported, not resolved.
- **Domestic price = foreign price.**
- **A unit climbs one level per tick**, and losing capital demotes immediately.

## Open design questions

Nothing below is implemented. The ledger already carries what each would need.

1. **Wages.** `buildings.csv` has value added per building, `labour.csv` the
   balance per class, and `REPORT.md` the bundle cost per worker. One option
   that uses only those: anchor each class's wage to its bundle cost and move it
   with that class's vacancies-versus-unemployed. Profit is then the residual.
2. **Standard of living.** With bundle size fixed, SoL cannot be quantity. It
   can be affordability: income per worker ÷ bundle cost. Below 1 needs a rule
   for which demand groups are cut first.
3. **Government balance.** A treasury/debt stock that the balance accrues to,
   with an umpire-set interest rate, matches the Guide's "Financial" OE line.
4. **Ownership and profit.** Entries are already keyed by owner. Profit could
   go to the budget (government), abroad (foreign), or split by a reinvestment
   rate (private): the reinvested share buys capital for that entry's pool,
   which is what drives upgrades.
5. **Price formation and trade.** Balances are currently valued at the foreign
   price and left open.
6. **Construction priority.** Pro rata by default; `["government"]` gives hard
   crowding out. A price for construction would replace both.
