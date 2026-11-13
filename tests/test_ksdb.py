"""Umpire database: the port matches the workbook, and the tick keeps its books."""
import unittest
from pathlib import Path

from ksdb import engine, store
from ksdb.store import Game, Recipe, Ref, Setting


def run(ref, game, n):
    state, out = None, []
    tick = game.start
    for _ in range(n):
        state, tables = engine.step(ref, game, tick, state)
        out.append(tables)
        tick = engine.next_tick(tick)
    return out


def example():
    ref = store.load_ref()
    return ref, store.load_game("example", ref)


class Port(unittest.TestCase):
    def test_reference_data_has_no_broken_references(self):
        ref, game = example()
        self.assertEqual(store.check(ref, game)[0], [])
        self.assertEqual(len(ref.recipes), 55)

    def test_consumption_matches_workbook_formula(self):
        # Consumption!I3:N3 with 10,000 L1 and dependency 0.5
        ref, game = example()
        rows = run(ref, game, 1)[0]["consumption"]
        got = {r["group"]: r["qty"] for r in rows if r["class"] == "L1"}
        want = {"Food": 1200, "Clothing": 1125, "Household": 1125, "Heating": 1200,
                "Leisure": 750, "Intoxicants": 900}
        for g, q in want.items():
            self.assertAlmostEqual(got[g], q)


class Population(unittest.TestCase):
    def test_flows_reconcile_and_promotions_keep_to_semesters(self):
        ref, game = example()
        ticks = run(ref, game, 24)
        prev = None
        for t in ticks:
            rows = {r["class"]: r for r in t["population"]}
            month = int(t["population"][0]["tick"][5:])
            if month not in game.promotion_months:
                self.assertEqual(sum(r["promoted_out"] for r in rows.values()), 0)
            self.assertEqual(rows["L1"]["promoted_out"], rows["L2"]["promoted_in"])
            if prev:
                for c, r in rows.items():
                    self.assertEqual(r["stock"], prev[c]["stock"] - r["promoted_out"] + r["promoted_in"]
                                     + r["births"] - r["deaths"] + r["migration"])
            prev = rows
        self.assertGreater(prev["L2"]["stock"], 0)

    def test_same_seed_same_history_and_new_seed_differs(self):
        ref, game = example()
        a = run(ref, game, 12)
        self.assertEqual(a, run(ref, game, 12))
        game.seed += 1
        self.assertNotEqual(a[-1]["population"], run(ref, game, 12)[-1]["population"])


class Exogenous(unittest.TestCase):
    def test_shock_overrides_then_lapses(self):
        s = {"x": [Setting("1920-01", "", "*", 1.0, 0), Setting("1920-03", "1920-04", "A", 0.5, 1),
                   Setting("1920-04", "", "*", 2.0, 2)]}
        get = lambda t: store.resolve(s, t, "x", "A", 9)
        self.assertEqual([get(f"1920-0{m}") for m in range(1, 6)], [1.0, 1.0, 0.5, 0.5, 2.0])
        self.assertEqual(store.resolve(s, "1919-12", "x", "A", 9), 9)


class Upgrades(unittest.TestCase):
    def test_capital_pool_to_levels_in_each_mode(self):
        # 5 units, 2,500 K1, level II needs 1,000 K1 per unit
        levels = [Recipe("Mine", 1, {}, {"L1": 1}, {"K1": 0}, {}, 0, True, []),
                  Recipe("Mine", 2, {}, {"L1": 1}, {"K1": 1000}, {}, 0, True, [])]
        self.assertEqual(engine.ladder(5, {"K1": 2500}, levels, "continuous"), {1: 2.5, 2: 2.5})
        self.assertEqual(engine.ladder(5, {"K1": 2500}, levels, "unit"), {1: 3.0, 2: 2.0})
        self.assertEqual(engine.ladder(5, {"K1": 2500}, levels, "building"), {1: 5})
        self.assertEqual(engine.ladder(5, {"K1": 5000}, levels, "building"), {2: 5})


def building_game(**params):
    """A builder making 10 construction a tick, and two owners each ordering a 20-unit farm."""
    R = lambda b, labour, cost, out: Recipe(b, 1, {}, {"L1": labour}, {}, out, cost, True, [])
    ref = Ref(classes=["L1"], goods=["Grain", "Construction"], capital={}, groups=[], weights={"L1": {}},
              group_goods={}, params={},
              recipes={"Builder": [R("Builder", 100, 0, {"Construction": 10})],
                       "Farm": [R("Farm", 10, 20, {"Grain": 1})]})
    P = {"bundle_scale": 0.1, "upgrade_mode": "continuous", "capital_depreciation": 0.0,
         "labour_downfill": True, "construction_good": "Construction", "construction_priority": [], **params}
    ev = lambda owner: {"tick": "1920-02", "building": "Farm", "owner": owner, "variable": "size", "value": "1"}
    game = Game(Path("."), "t", "1920-01", 1, [], P, {"L1": 1000},
                [{"building": "Builder", "owner": "private", "size": "1"}],
                events=[ev("government"), ev("private")])
    return ref, game


def built(tables, owner):
    return sum(r["units"] for r in tables["building_levels"] if r["building"] == "Farm" and r["owner"] == owner)


class Construction(unittest.TestCase):
    def test_capacity_is_shared_pro_rata_by_default(self):
        t = run(*building_game(), 3)
        self.assertAlmostEqual(built(t[1], "government"), 0.25)
        self.assertAlmostEqual(built(t[1], "private"), 0.25)
        self.assertAlmostEqual(sum(r["construction_done"] for r in t[1]["construction"]), 10)

    def test_government_priority_crowds_out_private_until_it_is_done(self):
        t = run(*building_game(construction_priority=["government"]), 5)
        self.assertEqual([round(built(x, "government"), 6) for x in t[1:]], [0.5, 1, 1, 1])
        self.assertEqual([round(built(x, "private"), 6) for x in t[1:]], [0, 0, 0.5, 1])

    def test_lumpy_mode_banks_construction_until_a_unit_is_paid_for(self):
        t = run(*building_game(upgrade_mode="unit", construction_priority=["government"]), 3)
        self.assertEqual(built(t[1], "government"), 0)
        self.assertEqual(built(t[2], "government"), 1)

    def test_what_is_built_starts_working_the_next_tick(self):
        t = run(*building_game(construction_priority=["government"]), 4)
        grain = lambda x: next(r["supply"] for r in x["goods_market"] if r["good"] == "Grain")
        self.assertEqual([round(grain(x), 6) for x in t], [0, 0, 0.5, 1])


if __name__ == "__main__":
    unittest.main()
