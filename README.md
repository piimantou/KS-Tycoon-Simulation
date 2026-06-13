# KS-Tycoon Simulation

The civilian-economy → procurement → manpower engine behind a Discord-mediated,
umpire-run Kriegsspiel. The economy feeds procurement, procurement and manpower
feed the (separate) tactical layer. See [`DESIGN.md`](DESIGN.md) for the full
design and the decisions behind it.

This repo contains the **deterministic engine core**, the **South Korea 1924**
validation scenario, and a **first-pass local web UI** for the umpire.

## Requirements

Python 3.11+. No third-party dependencies for the engine or tests (stdlib only).

## Quick start

```bash
# write the South Korea 1924 starting scenario
python -m kstycoon.cli new state.json

# resolve one financial year and print the handoff report
python -m kstycoon.cli report state.json

# resolve and save the resulting state for the next year
python -m kstycoon.cli tick state.json -o state_1925.json

# run the tests
python -m unittest discover -s tests
```

## Umpire web console

A dependency-free local web app (stdlib `http.server`): the umpire keys in the
year's directives — income tax, civilian/defense budget split, mobilisation
readiness, which projects to fund, and procurement orders — then runs the
financial year and reads back the handoff.

```bash
python -m kstycoon.web                 # http://127.0.0.1:8000
python -m kstycoon.web --port 9000 --state mygame.json
```

State is held in memory and persisted to the `--state` JSON file after each
year, so a game can be paused and resumed.

## What the engine does

Each call to `tick` resolves one financial year deterministically: advances
projects, sizes the manpower pool, drains conscripted labour from the economy,
runs sector production, clears a floating market, spends the defense budget on
unit tokens (domestic capacity first, then imports), mans the force (equipment
without men stays in training), reconciles the budget, and updates stability.
The output is a Markdown **handoff report** — the only thing that crosses into
the tactical Kriegsspiel.
