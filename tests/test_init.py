"""`init` maps the RevenueCat v2 API (recorded fixture, no network) to my/config.json
and my/products.json — and keeps my/*.example.json in sync with what it writes."""
import argparse
import contextlib
import io
import os
import tempfile
import unittest

from tests import helpers

# Shapes as returned by GET /projects/{id}/{offerings,paywalls,apps,offerings/{id}/packages?expand=items.product}
FIXTURE = {
    "/offerings": [
        {"id": "ofrng_main", "lookup_key": "default", "display_name": "Default", "is_current": True},
        {"id": "ofrng_b", "lookup_key": "experiment_b", "display_name": "B", "is_current": False},
    ],
    "/paywalls": [
        {"id": "pw_1", "name": "Main Paywall", "offering_id": "ofrng_main"},
        {"id": "pw_2", "name": "Holiday Test!", "offering_id": "ofrng_b"},
        {"id": "pw_3", "name": "Orphan", "offering_id": None},
    ],
    "/apps": [{"id": "app_ios", "type": "app_store"}, {"id": "app_play", "type": "play_store"}],
    "/offerings/ofrng_main/packages": [
        {"id": "pkg_1", "lookup_key": "$rc_annual", "display_name": "Annual", "products": {"items": [
            {"product": {"app_id": "app_ios", "store_identifier": "com.example.annual",
                         "subscription": {"duration": "P1Y", "trial_duration": "P7D"}}},
            {"product": {"app_id": "app_play", "store_identifier": "annual:annual-p1y",
                         "subscription": {"duration": "P1Y", "trial_duration": "P7D"}}},
        ]}},
        {"id": "pkg_2", "lookup_key": "$rc_monthly", "display_name": "Monthly", "products": {"items": [
            {"product": {"app_id": "app_ios", "store_identifier": "com.example.monthly",
                         "subscription": {"duration": "P1M", "trial_duration": None}}},
        ]}},
        {"id": "pkg_3", "lookup_key": "$rc_lifetime", "display_name": "Lifetime", "products": {"items": [
            {"product": {"app_id": "app_ios", "store_identifier": "com.example.lifetime", "subscription": None}},
        ]}},
    ],
}


class InitTests(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        self.tmp = tempfile.TemporaryDirectory()
        self.home = helpers.make_home(self.tmp.name)
        os.remove(os.path.join(self.home, "config.json"))     # a fresh clone has only the examples
        os.remove(os.path.join(self.home, "products.json"))
        self.lab = helpers.load_lab(self.home)
        self.calls = []

        def fake_api_list(path, cfg=None):
            self.calls.append(path)
            return FIXTURE[path.split("?")[0]]
        self.lab.api_list = fake_api_list

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self.tmp.cleanup()

    def _init(self, project="proj_test"):
        with contextlib.redirect_stdout(io.StringIO()):
            self.lab.cmd_init(argparse.Namespace(project=project))

    def test_iso_period(self):
        p = self.lab._iso_period
        self.assertEqual(p("P1Y"), {"unit": "year", "count": 1})
        self.assertEqual(p("P3M"), {"unit": "month", "count": 3})
        self.assertEqual(p("P1W"), {"unit": "week", "count": 1})
        self.assertEqual(p("P14D"), {"unit": "day", "count": 14})
        self.assertIsNone(p(None))
        self.assertIsNone(p("P1Y2M"))

    def test_init_requires_a_project_id(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.lab.cmd_init(argparse.Namespace(project=None))
        self.assertFalse(os.path.isfile(os.path.join(self.home, "config.json")))

    def test_config_registry_from_fixture(self):
        self._init()
        cfg = helpers.read_json(os.path.join(self.home, "config.json"))
        self.assertEqual(cfg["project_id"], "proj_test")
        self.assertNotIn("REPLACE", helpers.read_text(os.path.join(self.home, "config.json")))
        self.assertEqual(set(cfg["paywalls"]), {"main-paywall", "holiday-test", "orphan"})
        self.assertEqual(cfg["paywalls"]["main-paywall"], {"id": "pw_1", "offering_id": "ofrng_main",
                                                           "label": "Main Paywall (offering: default — CURRENT)"})
        self.assertEqual(cfg["paywalls"]["orphan"]["label"], "Orphan (no offering)")
        self.assertEqual(cfg["default_paywall"], "main-paywall")   # the one on the current offering
        example = helpers.read_json(os.path.join(helpers.MY_TEMPLATE, "config.example.json"))
        self.assertEqual(set(example) - {"_comment"} - set(cfg), set(), "config.example.json has keys init drops")
        self.assertNotIn("_comment", cfg)

    def test_products_skeleton_from_current_offering(self):
        self._init()
        prods = helpers.read_json(os.path.join(self.home, "products.json"))
        self.assertIn("PRICES", prods["_comment"])
        by_id = {p["identifier"]: p for p in prods["packages"]}
        self.assertEqual(list(by_id), ["$rc_annual", "$rc_monthly", "$rc_lifetime"])
        annual = by_id["$rc_annual"]
        self.assertEqual(annual["name"], "Annual")
        self.assertEqual(annual["price"], {"amount": 0.0, "currency": "USD"})
        self.assertEqual(annual["period"], {"unit": "year", "count": 1})
        self.assertEqual(annual["trial"], {"unit": "day", "count": 7})
        self.assertEqual(annual["ios"], {"product_id": "com.example.annual"})
        self.assertEqual(annual["android"], {"product_id": "annual:annual-p1y"})
        self.assertIsNone(by_id["$rc_monthly"]["trial"])
        self.assertEqual(by_id["$rc_monthly"]["period"], {"unit": "month", "count": 1})
        self.assertNotIn("android", by_id["$rc_monthly"])
        self.assertEqual(by_id["$rc_lifetime"]["period"], {"unit": "month", "count": 1})   # documented default
        # same keys as the example file (minus prices, which the API doesn't have)
        example = helpers.read_json(os.path.join(helpers.MY_TEMPLATE, "products.example.json"))["packages"][0]
        self.assertEqual(set(example) - set(annual), set())
        self.assertTrue(any(c.startswith("/offerings/ofrng_main/packages?expand=items.product") for c in self.calls))

    def test_init_is_idempotent_and_keeps_edits(self):
        self._init()
        prods_path = os.path.join(self.home, "products.json")
        prods = helpers.read_json(prods_path)
        prods["packages"][0]["price"]["amount"] = 59.99
        self.lab.save_json(prods_path, prods)
        cfg_path = os.path.join(self.home, "config.json")
        cfg = helpers.read_json(cfg_path)
        cfg["paywalls"]["main-paywall"]["label"] = "edited"
        self.lab.save_json(cfg_path, cfg)
        self._init(project=None)   # project id comes from the existing config
        self.assertEqual(helpers.read_json(prods_path)["packages"][0]["price"]["amount"], 59.99)
        cfg = helpers.read_json(cfg_path)
        self.assertEqual(cfg["paywalls"]["main-paywall"]["label"], "edited")
        self.assertEqual(len(cfg["paywalls"]), 3)

    def test_no_current_offering_falls_back_to_example_products(self):
        self.lab.api_list = lambda path, cfg=None: (
            [dict(o, is_current=False) for o in FIXTURE["/offerings"]] if path == "/offerings"
            else FIXTURE[path.split("?")[0]])
        self._init()
        prods = helpers.read_json(os.path.join(self.home, "products.json"))
        self.assertEqual([p["identifier"] for p in prods["packages"]], ["$rc_annual", "$rc_monthly"])
        cfg = helpers.read_json(os.path.join(self.home, "config.json"))
        self.assertEqual(cfg["default_paywall"], "main-paywall")   # first registered


if __name__ == "__main__":
    unittest.main()
