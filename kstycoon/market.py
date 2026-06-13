"""Floating-market price clearing.

A deliberately small tâtonnement: each iteration nudges every good's price
toward the level that closes its demand/supply gap, damped for stability and
clamped to a band around the base price (Vic3-style ±band). This is the step
that makes scarcity bite — flood demand for a military input and its price
climbs toward the cap, making procurement dearer.
"""

from __future__ import annotations

from .config import Config
from . import model as m


def clear_market(
    goods: dict[str, m.Good],
    supply: dict[str, float],
    demand: dict[str, float],
    cfg: Config,
) -> dict[str, m.Good]:
    """Update ``goods`` prices in place toward demand/supply equilibrium.

    Imports are treated as perfectly elastic supply at the good's exogenous
    ``import_price`` (set by the umpire), so an importable good's domestic price
    is also capped at that import price — you would never pay more at home than
    to ship it in.
    """
    for _ in range(cfg.market_iterations):
        for gid, good in goods.items():
            s = supply.get(gid, 0.0)
            d = demand.get(gid, 0.0)
            if d <= 0 and s <= 0:
                continue
            # ratio > 1 means excess demand -> push price up
            ratio = (d + 1e-9) / (s + 1e-9)
            target = good.base_price * (ratio ** cfg.price_elasticity)
            new_price = good.price + cfg.market_damping * (target - good.price)

            lo = good.base_price * (1 - cfg.price_band)
            hi = good.base_price * (1 + cfg.price_band)
            new_price = max(lo, min(hi, new_price))

            if good.importable and good.import_price is not None:
                new_price = min(new_price, good.import_price)

            good.price = new_price
    return goods
