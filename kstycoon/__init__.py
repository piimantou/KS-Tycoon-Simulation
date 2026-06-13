"""KS-Tycoon — economic / procurement / manpower engine for a Kriegsspiel.

The engine is a pure, deterministic annual-tick simulator. It is intentionally
Discord-free and UI-free: the umpire (and, later, a local web app) drive it by
loading a scenario, recording each year's directives, and running ``tick``.

The single deliverable that crosses into the tactical Kriegsspiel is the
*handoff report* produced by :mod:`kstycoon.report` — a roster of operational
unit tokens (men + equipment + upkeep) plus capital works.
"""

__all__ = ["model", "config", "resolve", "market", "report", "serialize"]
