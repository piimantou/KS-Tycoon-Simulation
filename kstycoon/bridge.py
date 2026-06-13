"""Backend-free bridge between a front-end and the engine.

This module has **no I/O dependencies** (no http, no sockets), so it runs both
under the local web server (:mod:`kstycoon.web`) and in the browser via Pyodide.
Everything crosses the boundary as JSON strings, keeping the JS/Python interface
trivial.
"""

from __future__ import annotations

import json

from . import model as m
from . import report as report_mod
from . import serialize
from .resolve import tick
from .scenarios import south_korea_y0


def _apply_decisions(state: m.GameState, decisions: dict) -> None:
    g = state.government
    if "income_tax_rate" in decisions:
        g.income_tax_rate = float(decisions["income_tax_rate"])
    if "civilian_share" in decisions:
        g.civilian_share = float(decisions["civilian_share"])
    if "defense_share" in decisions:
        g.defense_share = float(decisions["defense_share"])
    if "readiness" in decisions:
        state.manpower.readiness = int(decisions["readiness"])
    state.new_project_ids = list(decisions.get("new_project_ids", []))
    state.procurement_orders = [
        m.ProcurementOrder(
            unit_token_id=o["unit_token_id"],
            channel=o["channel"],
            quantity=int(o["quantity"]),
        )
        for o in decisions.get("procurement_orders", [])
    ]


def run_year(state: m.GameState, decisions: dict) -> tuple[m.GameState, dict]:
    """Apply this year's directives and resolve one financial year.
    Returns (new_state, payload) where payload is JSON-serialisable."""
    _apply_decisions(state, decisions)
    res = tick(state)
    payload = {
        "report": report_mod.render(res),
        "state": serialize.to_dict(res.state),
        "result": {
            "operational_tokens": res.operational_tokens,
            "training_tokens": res.training_tokens,
            "delivered": res.delivered,
            "manpower_available": res.manpower_available,
            "manpower_operational": res.manpower_operational,
            "personnel_cost": res.personnel_cost,
            "procurement_cost": res.procurement_cost,
            "project_cost": res.project_cost,
            "warnings": res.warnings,
        },
    }
    return res.state, payload


# --- string-in / string-out wrappers, convenient to call from JS (Pyodide) --- #
def new_state_json() -> str:
    return json.dumps(serialize.to_dict(south_korea_y0.build()))


def tick_json(state_json: str, decisions_json: str) -> str:
    state = serialize.from_dict(json.loads(state_json))
    _, payload = run_year(state, json.loads(decisions_json))
    return json.dumps(payload)
