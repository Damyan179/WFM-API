"""Offline tests: the HTTP layer is replaced with canned data. Run:  python -m unittest discover tests"""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wfm import auth, catalog, client, market, repricer

NOW = datetime.now(timezone.utc)
iso = lambda days: (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

ITEMS = [
    {"id": "a", "slug": "rhino_prime_set", "tags": ["prime", "set"], "i18n": {"en": {"name": "Rhino Prime Set"}}},
    {"id": "b", "slug": "rhino_prime_systems", "tags": ["prime", "component"], "i18n": {"en": {"name": "Rhino Prime Systems Blueprint"}}},
    {"id": "c", "slug": "lith_a1_relic", "tags": ["relic"], "i18n": {"en": {"name": "Lith A1 Relic"}}},
    {"id": "d", "slug": "sunset_scene", "tags": [], "i18n": {"en": {"name": "Sunset Scene"}}},
]
DUCATS = {"payload": {"previous_day": [{"item": "a", "wa_price": 120.5}, {"item": "b", "wa_price": 30, "ducats": 45},
                                       {"item": "d", "wa_price": 50}],
                      "previous_hour": [{"item": "b", "wa_price": 33}]}}


def order(oid, plat, status="ingame", typ="sell", rank=None, subtype=None, updated=0, visible=True):
    o = {"id": oid, "type": typ, "platinum": plat, "quantity": 1, "visible": visible, "itemId": "b",
         "createdAt": iso(400), "updatedAt": iso(updated), "user": {"ingameName": f"u{oid}", "status": status}}
    if rank is not None: o["rank"] = rank
    if subtype: o["subtype"] = subtype
    return o


class Fake:
    def __init__(self): self.books, self.mine, self.patches, self.fail, self.posts = {}, [], [], set(), []
    def request(self, method, url, token=None, json=None, extra_headers=None, raw=False):
        if url.endswith("/items"): return {"data": ITEMS}
        if url.endswith("/tools/ducats"): return DUCATS
        if url.endswith("/orders/my"): return {"data": self.mine}
        if "/orders/item/" in url:
            slug = url.rsplit("/", 1)[1]
            if slug in self.fail: raise client.WfmError("boom", 500)
            return {"data": self.books.get(slug, [])}
        if method == "POST" and url.endswith("/order"):
            self.posts.append(json); return {"data": {"id": "new1", **json}}
        if method == "PATCH":
            oid = url.rsplit("/", 1)[1]
            if oid in self.fail: raise client.WfmError("HTTP 400: nope", 400)
            self.patches.append((oid, json)); return {}
        raise AssertionError(url)


_ORIGINALS = (client.request, client.get, client.patch)


class Core(unittest.TestCase):
    def tearDown(self):
        client.request, client.get, client.patch = _ORIGINALS

    def setUp(self):
        self.fake = Fake()
        client.request = self.fake.request
        client.get = lambda url, token=None: self.fake.request("GET", url, token)
        client.patch = lambda url, token, json: self.fake.request("PATCH", url, token, json)
        catalog._items = None; catalog._stats = None
        catalog._read_disk_cache = lambda: (0.0, None)
        catalog.ITEMS_CACHE = Path("/tmp/wfm-test-items.json"); catalog.CACHE_DIR = Path("/tmp")

    def test_pick_price_original_behaviour(self):
        pp = repricer.pick_price
        self.assertEqual(pp([10, 11, 12, 13, 20]), 12)
        self.assertEqual(pp([10, 10, 10, 50, 60]), 49)
        self.assertEqual(pp([1, 20, 21, 22, 23, 24]), 22)          # the 1p troll is ignored
        self.assertIsNone(pp([10, 11, 12]))                        # fewer than 4 offers
        self.assertEqual(pp([10, 11, 12, 13], wa_price=30), None)  # all below 70% of the average
        self.assertEqual(pp([40, 41, 42, 43], wa_price=30), 39)    # capped at 130% of the average

    def test_pick_price_settings(self):
        s = repricer.Settings(top_n=1)
        self.assertEqual(repricer.pick_price([10, 12, 14], settings=s), 9)
        s = repricer.Settings(top_n=2, min_price=15)
        self.assertEqual(repricer.pick_price([10, 12, 14], settings=s), 15)

    def test_find_item_and_slug_validation(self):
        self.assertEqual(catalog.find_item("rhino prime set")["id"], "a")
        self.assertEqual(catalog.find_item("  Rhino   Prime SET ")["id"], "a")
        self.assertEqual(catalog.find_item("lith a1")["id"], "c")
        with self.assertRaises(ValueError): catalog.find_item("rhino")       # ambiguous
        with self.assertRaises(ValueError): catalog.find_item("nope")
        with self.assertRaises(ValueError): market.fetch_orders("../v1/auth?x=1")
        with self.assertRaises(ValueError): catalog.to_slug("a/b")

    def test_top_prices_set_detection(self):
        self.assertEqual([r["name"] for r in market.top_prices("day", "sets")], ["Rhino Prime Set"])
        comps = [r["name"] for r in market.top_prices("day", "components")]
        self.assertEqual(comps, ["Sunset Scene", "Rhino Prime Systems Blueprint"])  # 'Sunset' is not a set
        self.assertEqual(len(market.top_prices("day", "components", min_price=40)), 1)
        self.assertEqual(market.average_price(ITEMS[1]), {"day": 30, "hour": 33})
        self.assertEqual(market.average_price(ITEMS[2]), {"day": None, "hour": None})

    def test_list_orders_grouping_and_dates(self):
        self.fake.books["rhino_prime_systems"] = [
            order("1", 30), order("2", 25), order("3", 28, "online"), order("4", 20, "offline", updated=5),
            order("5", 5, "offline", updated=45), order("6", 99, typ="buy"), order("7", 1, visible=False)]
        g = market.list_orders("rhino_prime_systems")
        self.assertEqual([r["platinum"] for r in g["ingame"]], [25, 30])
        self.assertEqual([r["platinum"] for r in g["online"]], [28])
        self.assertEqual([r["platinum"] for r in g["offline"]], [20])   # the 45-day-old order is dropped
        self.assertEqual([r["platinum"] for r in market.list_orders("rhino_prime_systems", "buy")["ingame"]], [99])

    def test_build_and_apply_plan(self):
        f = self.fake
        f.mine = [dict(order("m1", 50), itemId="b"), dict(order("m2", 10, subtype="radiant"), itemId="c"),
                  dict(order("m3", 5), itemId="a"), dict(order("m4", 9, typ="buy"), itemId="b"),
                  dict(order("m5", 26), itemId="d")]
        f.books["rhino_prime_systems"] = [order("m1", 50)] + [order(str(i), p) for i, p in enumerate([24, 25, 26, 27, 28])]
        f.books["lith_a1_relic"] = ([order(f"i{i}", 2, subtype="intact") for i in range(6)]
                                    + [order("r1", 12, subtype="radiant"), order("r2", 13, subtype="radiant"),
                                       order("r3", 14, "online", subtype="radiant"), order("r4", 15, "online", subtype="radiant")])
        f.fail.add("rhino_prime_set")
        f.books["sunset_scene"] = [order(str(i), p) for i, p in enumerate([40, 40, 40, 40])]
        seen = []
        plan = repricer.build_plan("tok", progress=lambda i, n, name: seen.append((i, n)))
        self.assertEqual(seen[-1], (4, 4))                       # the buy order is not included
        by = {p.order_id: p for p in plan}
        self.assertEqual(by["m1"].proposed, 26)
        self.assertEqual(by["m2"].proposed, 14)                  # radiant only, with the online fallback
        self.assertIn("online", by["m2"].note)
        self.assertFalse(by["m3"].changed); self.assertIn("Could not read", by["m3"].note)   # one failure does not stop the run
        self.assertEqual(by["m5"].proposed, 40)

        no_fallback = repricer.build_plan("tok", repricer.Settings(use_online_fallback=False))
        self.assertFalse({p.order_id: p for p in no_fallback}["m2"].changed)

        f.fail.add("m5")
        done = repricer.apply_plan("tok", plan)
        self.assertEqual(done, 2)
        self.assertEqual(sorted(f.patches), [("m1", {"platinum": 26}), ("m2", {"platinum": 14})])
        self.assertTrue(by["m5"].result.startswith("Failed")); self.assertTrue(by["m5"].changed)
        self.assertEqual(by["m1"].current, 26); self.assertFalse(by["m1"].changed)

    def test_large_changes_are_flagged(self):
        f = self.fake
        f.mine = [dict(order("m1", 50), itemId="b"), dict(order("m2", 22), itemId="b")]
        f.books["rhino_prime_systems"] = [order(str(i), p) for i, p in enumerate([24, 25, 26, 27, 28])]
        by = {p.order_id: p for p in repricer.build_plan("tok")}
        self.assertTrue(by["m1"].flagged); self.assertIn("-48%", by["m1"].note)      # 50 -> 26
        self.assertFalse(by["m2"].flagged)                                           # 22 -> 26 is +18%
        loose = {p.order_id: p for p in repricer.build_plan("tok", repricer.Settings(max_change=0.6))}
        self.assertFalse(loose["m1"].flagged)

    def test_order_ids_are_validated_before_use_in_urls(self):
        for bad in ("../orders/group/all", "a/b", "", None, "x" * 65, "id?x=1"):
            with self.assertRaises(ValueError): repricer.set_quantity("tok", bad, 1)
            with self.assertRaises(ValueError): repricer.delete_order("tok", bad)
        repricer.set_quantity("tok", "696be7ee6a51e1b3b0c3575d", 2)
        self.assertEqual(self.fake.patches[-1][0], "696be7ee6a51e1b3b0c3575d")

    def test_unchanged_price_is_not_patched(self):
        self.fake.mine = [dict(order("m1", 26), itemId="b")]
        self.fake.books["rhino_prime_systems"] = [order(str(i), p) for i, p in enumerate([24, 25, 26, 27])]
        plan = repricer.build_plan("tok")
        self.assertFalse(plan[0].changed)
        self.assertEqual(repricer.apply_plan("tok", plan), 0); self.assertEqual(self.fake.patches, [])

    def test_suggest_price_and_create(self):
        f = self.fake
        f.books["rhino_prime_systems"] = [order(str(i), p) for i, p in enumerate([24, 25, 26, 27, 28])]
        price, note = repricer.suggest_price(ITEMS[1])
        self.assertEqual(price, 26); self.assertIn("5 in-game", note)
        f.books["rhino_prime_systems"] = [order("1", 25)]
        price, note = repricer.suggest_price(ITEMS[1])                 # too few sellers -> 24h average
        self.assertEqual(price, 30); self.assertIn("24h average", note)
        with self.assertRaises(ValueError): repricer.suggest_price(ITEMS[2])   # no sellers, no average
        made = repricer.create_sell_order("tok", ITEMS[1], 26, 2)
        self.assertEqual(made["id"], "new1")
        self.assertEqual(f.posts, [{"itemId": "b", "type": "sell", "platinum": 26, "quantity": 2, "visible": True}])
        with self.assertRaises(ValueError): repricer.create_sell_order("tok", ITEMS[1], 0, 1)

    def test_list_orders_and_quantity(self):
        f = self.fake
        f.mine = [dict(order("m1", 50), itemId="b", quantity=3), dict(order("m4", 9, typ="buy"), itemId="b"),
                  dict(order("m9", 7), itemId="unknown")]
        listing = repricer.list_orders("tok")
        self.assertEqual([(p.order_id, p.quantity, p.current, p.changed) for p in listing], [("m1", 3, 50, False)])
        repricer.set_quantity("tok", "m1", 5)
        self.assertEqual(f.patches, [("m1", {"quantity": 5})])
        with self.assertRaises(ValueError): repricer.set_quantity("tok", "m1", 0)

    def test_token_validity_distinguishes_network_errors(self):
        def get(url, token=None): raise client.WfmError("HTTP 401", 401)
        client.get = get
        self.assertFalse(auth.token_is_valid("x"))
        def get2(url, token=None): raise client.WfmError("Network error")
        client.get = get2
        with self.assertRaises(client.WfmError): auth.token_is_valid("x")


if __name__ == "__main__":
    unittest.main()
