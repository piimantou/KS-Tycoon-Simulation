"""Engine tests. Stdlib unittest so they always run (no pytest dependency).

    python -m unittest discover -s tests
"""

from __future__ import annotations

import copy
import unittest

from kstycoon import serialize
from kstycoon.resolve import tick
from kstycoon.scenarios import south_korea_y0


class ScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = south_korea_y0.build()

    def test_headline_numbers(self):
        s = self.state
        self.assertEqual(s.manpower.population, 11_560_000)
        self.assertAlmostEqual(s.labour_force, 4_855_200, places=0)
        # GDP per capita from the source sheet
        self.assertAlmostEqual(s.gdp / s.manpower.population, 380.6, places=1)

    def test_manpower_tiers_match_source(self):
        mp = self.state.manpower
        self.assertAlmostEqual(mp.population * mp.volunteer_fraction, 115_600)
        self.assertAlmostEqual(mp.population * mp.conscription_i_fraction, 1_156_000)
        self.assertAlmostEqual(mp.population * mp.conscription_ii_fraction, 2_196_400)

    def test_serialize_roundtrip(self):
        data = serialize.to_dict(self.state)
        back = serialize.from_dict(data)
        self.assertEqual(serialize.to_dict(back), data)


class TickTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = south_korea_y0.build()

    def test_determinism(self):
        a = tick(copy.deepcopy(self.state))
        b = tick(copy.deepcopy(self.state))
        self.assertEqual(serialize.to_dict(a.state), serialize.to_dict(b.state))

    def test_year_advances_and_inputs_reset(self):
        res = tick(self.state)
        self.assertEqual(res.state.year, 1925)
        self.assertEqual(res.state.procurement_orders, [])
        self.assertEqual(res.state.new_project_ids, [])

    def test_domestic_procurement_gated_by_capacity(self):
        # scenario orders 20 domestic rifles; small_arms capacity is exactly 20
        res = tick(self.state)
        self.assertEqual(res.delivered["rifles"]["domestic"], 20)
        self.assertEqual(res.delivered["rifles"]["import"], 100)

    def test_imports_delivered_and_operational(self):
        res = tick(self.state)
        # readiness 1 pool (115,600) easily mans the few thousand men in tokens
        self.assertEqual(res.operational_tokens.get("light_field_gun", 0), 20)
        self.assertEqual(res.operational_tokens.get("truck", 0), 15)
        self.assertFalse(any(res.training_tokens.values()))

    def test_training_gate_when_manpower_starved(self):
        # drop the volunteer pool to a handful of men -> equipment can't be manned
        self.state.manpower.volunteer_fraction = 0.0000001  # ~1 person
        res = tick(self.state)
        self.assertTrue(any(res.training_tokens.values()))

    def test_incomes_distributed_with_inequality(self):
        res = tick(self.state)
        pops = res.state.pops
        for p in pops.values():
            self.assertGreater(p.income, 0.0)
        # owners (upper) earn far more per capita than peasants (lower)
        upper_pc = pops["upper"].income / pops["upper"].size
        rural_pc = pops["rural_lower"].income / pops["rural_lower"].size
        self.assertGreater(upper_pc, rural_pc)

    def test_revenue_funds_budget(self):
        res = tick(self.state)
        g = res.state.government
        total_income = sum(p.income for p in res.state.pops.values())
        # revenue is at least the income-tax take (plus any state surplus)
        self.assertGreaterEqual(g.revenue, total_income * g.income_tax_rate - 1.0)
        self.assertAlmostEqual(g.defense_budget, g.revenue * g.defense_share, places=2)
        self.assertAlmostEqual(g.civilian_budget, g.revenue * g.civilian_share, places=2)

    def test_gdp_calibrated_near_source(self):
        res = tick(self.state)
        pc = res.state.gdp / res.state.manpower.population
        self.assertTrue(350 <= pc <= 410, f"GDP/capita {pc:.0f} off calibration")

    def test_higher_tax_raises_revenue(self):
        low = tick(copy.deepcopy(self.state)).state.government.revenue
        self.state.government.income_tax_rate = 0.30
        high = tick(self.state).state.government.revenue
        self.assertGreater(high, low)

    def test_project_completes_after_lead_time(self):
        s = self.state
        # BOSCO has a 3-year lead; small_arms capacity should jump by +60 then.
        for _ in range(2):
            res = tick(s)
            s = res.state
        before = s.arms["small_arms"].capacity
        res = tick(s)  # third tick -> completion
        self.assertGreater(res.state.arms["small_arms"].capacity, before)


class WebAppTests(unittest.TestCase):
    def _app(self):
        import tempfile

        from kstycoon.web import _App

        path = tempfile.mktemp(suffix=".json")
        return _App(path)

    def test_apply_and_tick_applies_decisions(self):
        app = self._app()
        out = app.apply_and_tick(
            {
                "income_tax_rate": 0.20,
                "civilian_share": 0.5,
                "defense_share": 0.5,
                "readiness": 1,
                "new_project_ids": ["bosco"],
                "procurement_orders": [
                    {"unit_token_id": "rifles", "channel": "import", "quantity": 50}
                ],
            }
        )
        self.assertIn("report", out)
        self.assertEqual(out["state"]["year"], 1925)
        self.assertEqual(out["state"]["government"]["income_tax_rate"], 0.20)
        self.assertEqual(out["result"]["delivered"]["rifles"]["import"], 50)
        # state persisted across the tick
        self.assertEqual(app.state.year, 1925)


if __name__ == "__main__":
    unittest.main()
