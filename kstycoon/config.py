"""Tunable engine constants.

Everything here is a *dial* the umpire/designer is expected to turn while
balancing the game. Nothing in the resolver hard-codes these values directly;
they are passed in via :class:`Config` so a scenario can override them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    # --- market clearing (tâtonnement) ---
    price_elasticity: float = 0.5      # how hard price reacts to demand/supply gap
    price_band: float = 0.75           # prices stay within ±75% of base (Vic3-style)
    market_iterations: int = 25        # fixed-point iterations per year
    market_damping: float = 0.5        # damping on price updates for stability

    # --- per-period equilibrium ---
    # The economy is solved to a (fuzzy) equilibrium each period by iterating
    # incomes <-> consumption <-> prices to a joint fixed point, rather than
    # taking a single damped step and advancing. This kills year-to-year
    # oscillation: the reported year IS the settled state.
    equilibrium_iterations: int = 60
    equilibrium_tol: float = 1e-4      # stop early when prices stop moving

    # --- manpower ---
    # Readiness level -> which manpower tiers are callable (cumulative).
    # 1 Routine, 2 Alert, 3 Partial mobilization, 4 General mobilization.
    conscript_wage_factor: float = 0.5  # conscripts paid half a volunteer's wage

    # --- stability ---
    # Standard-of-living below this fraction of needs erodes loyalty.
    sol_satisfaction_floor: float = 0.6
    stability_sol_weight: float = 0.5

    # --- procurement ---
    # Fraction of the defense budget reserved for upkeep before new orders.
    upkeep_reserve_fraction: float = 0.0  # 0 = upkeep billed against remainder
