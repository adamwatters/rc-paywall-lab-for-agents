"""paywall_dsl emits shapes lint accepts; every library design generates clean and
deterministically; the library index/catalog list every design."""
import json
import os
import re
import struct
import tempfile
import unittest

from tests import helpers
from tests.helpers import ROOT

import lab_lint
import paywall_dsl as dsl


class DslPrimitives(unittest.TestCase):
    def test_lid_is_api_shaped_and_stable(self):
        a, b = dsl.lid("headline"), dsl.lid("headline")
        self.assertEqual(a, b)
        self.assertRegex(a, lab_lint.LID_RE)
        self.assertNotEqual(a, dsl.lid("headline2"))

    def test_image_urls_has_all_five_fields(self):
        src = dsl.image_urls("bg.png", 200, 400)["light"]
        for k in lab_lint.IMAGE_URL_FIELDS:
            self.assertTrue(src.get(k), k)
        self.assertEqual((src["width"], src["height"]), (200, 400))

    def test_eligibility_siblings_base_state_is_ineligible(self):
        dsl.reset_ids()
        trial, plain = dsl.eligibility_siblings(dsl.stack([]), dsl.stack([]))
        self.assertIs(trial["visible"], False)
        self.assertEqual(trial["overrides"], [{"conditions": [dsl.INTRO], "properties": {"visible": True}}])
        self.assertNotIn("visible", plain)   # base-visible
        self.assertEqual(plain["overrides"], [{"conditions": [dsl.INTRO], "properties": {"visible": False}}])
        self.assertIn(dsl.INTRO["type"], lab_lint.KNOWN_CONDITIONS)

    def test_trial_days(self):
        self.assertEqual(dsl.trial_days({"trial": {"unit": "week", "count": 1}}), 7)
        self.assertEqual(dsl.trial_days({"trial": None}), 0)
        self.assertEqual(dsl.trial_days({}), 0)

    def test_ids_are_deterministic_after_reset(self):
        dsl.reset_ids()
        a = dsl.text(dsl.lid("x"))["id"]
        dsl.reset_ids()
        self.assertEqual(a, dsl.text(dsl.lid("x"))["id"])

    def test_write_png_and_mesh_gradient_are_valid_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a", "b.png")
            dsl.write_png(p, 3, 2, lambda x, y: (x, y, 0, 255))
            data = helpers.read_text(p, "rb")
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            w, h = struct.unpack(">II", data[16:24])
            self.assertEqual((w, h), (3, 2))
            g = os.path.join(tmp, "g.png")
            dsl.mesh_gradient(g, 4, 4, [((0, 0), (255, 0, 0)), ((1, 1), (0, 0, 255))])
            self.assertEqual(struct.unpack(">II", helpers.read_text(g, "rb")[16:24]), (4, 4))


class LibraryDesigns(unittest.TestCase):
    """The two library designs are the regression suite; without a simulator this is
    the half of it that can run anywhere."""

    def test_every_design_generates_lint_clean(self):
        prods = helpers.products()
        with tempfile.TemporaryDirectory() as tmp:
            home = helpers.make_home(tmp)
            for slug in helpers.list_designs():
                with self.subTest(design=slug):
                    var_dir, var = helpers.generate_design(slug, home)
                    findings = lab_lint.lint(var, helpers.ui_config(), prods,
                                             assets_dir=os.path.join(var_dir, "assets"))
                    self.assertEqual([], [f"{f.level} {f.rule}: {f.message}" for f in findings])
                    self.assertEqual(var["default_locale"], "en_US")
                    self.assertEqual(var["components_config"]["base"]["stack"]["type"], "stack")

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = helpers.make_home(tmp)
            for slug in helpers.list_designs():
                with self.subTest(design=slug):
                    var_dir, first = helpers.generate_design(slug, home)
                    _, second = helpers.generate_design(slug, home)
                    self.assertEqual(first, second)

    def test_designs_use_every_package(self):
        prods = helpers.products()
        with tempfile.TemporaryDirectory() as tmp:
            home = helpers.make_home(tmp)
            for slug in helpers.list_designs():
                with self.subTest(design=slug):
                    _, var = helpers.generate_design(slug, home)
                    used = set(re.findall(r'"package_id": "([^"]+)"', json.dumps(var)))
                    self.assertEqual(used, {p["identifier"] for p in prods["packages"]})

    def test_library_index_and_catalog_list_every_design(self):
        designs = helpers.list_designs()
        catalog = helpers.read_json(os.path.join(ROOT, "library", "catalog.json"))
        self.assertEqual(sorted(d["name"] for d in catalog["designs"]), designs)
        index = helpers.read_text(os.path.join(ROOT, "library", "INDEX.md"))
        for slug in designs:
            self.assertIn(f"[{slug}](designs/{slug}/)", index)
            d = os.path.join(helpers.DESIGNS, slug)
            self.assertTrue(os.path.isfile(os.path.join(d, "README.md")), f"{slug}/README.md")
            for shot in ("ios-eligible", "ios-trial-used", "android-eligible", "android-trial-used"):
                self.assertTrue(os.path.isfile(os.path.join(d, "screenshots", shot + ".png")), f"{slug}: {shot}")
        for r in catalog["recipes"]:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "library", "recipes", r["name"] + ".md")), r["name"])


if __name__ == "__main__":
    unittest.main()
