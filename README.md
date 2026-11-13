# KS-Tycoon Simulation

The umpire's database for the *Kriegsspiel Economic System - Expanded* design:
the Economic Tables workbook as plain-text tables, plus a small engine that
resolves monthly ticks into a ledger. Git is the history.

See [`db/README.md`](db/README.md) for the layout, the turn procedure, what a
tick computes, and the open design questions.

## Requirements

Python 3.12+. No third-party dependencies.

## Quick start

```bash
# list broken references and unfilled data
python -m ksdb check example

# resolve the next tick and regenerate db/games/example/REPORT.md
python -m ksdb advance example

# run the tests
python -m unittest discover -s tests
```
