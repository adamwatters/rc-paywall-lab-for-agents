"""`render` produces what the harnesses consume; lab home resolution; `new` from a variation."""
import argparse
import contextlib
import io
import os
import tempfile
import unittest

from tests import helpers
from tests.helpers import ROOT

import lab_lint
import paywall_dsl as dsl


class RenderTests(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        self._cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = helpers.make_home(self.tmp.name)
        self.lab = helpers.load_lab(self.home)

    def tearDown(self):
        os.chdir(self._cwd)
        os.environ.clear()
        os.environ.update(self._env)
        self.tmp.cleanup()

    def _variation(self, name, var, assets=None):
        d = os.path.join(self.home, "variations", name)
        os.makedirs(d)
        self.lab.save_json(os.path.join(d, "paywall.json"), var)
        for fname in assets or []:
            dsl.write_png(os.path.join(d, "assets", fname), 4, 4, lambda x, y: (255, 0, 0, 255))
        return d

    def test_render_writes_everything_the_harnesses_read(self):
        dsl.reset_ids()
        S = dsl.Strings()
        img = dsl.image("hero.png", 4, 4)
        img["source"]["light"] = {"width": 4, "height": 4, "original": img["source"]["light"]["original"]}  # only `original`
        var = dsl.paywall(dsl.stack([img, dsl.text(S.add("t", "Hi"))]), S, background=dsl.image_background("bg.png", 4, 4))
        self._variation("v", var, assets=["hero.png", "bg.png"])

        with contextlib.redirect_stdout(io.StringIO()):
            res = self.lab.render("v")
        self.assertTrue(os.path.isabs(res))
        offerings = helpers.read_json(os.path.join(res, "qa", "offerings.json"))
        off = offerings["offerings"][0]
        self.assertEqual(offerings["current_offering_id"], off["identifier"])
        pc = off["paywall_components"]
        self.assertEqual(pc["template_name"], "components")
        self.assertEqual(pc["default_locale"], "en_US")
        self.assertIn("en_US", pc["components_localizations"])
        # packages embedded in SDK wire shape, bound to the iOS product ids
        prods = helpers.products()["packages"]
        self.assertEqual([p["identifier"] for p in off["packages"]], [p["identifier"] for p in prods])
        self.assertEqual([p["platform_product_identifier"] for p in off["packages"]],
                         [p["ios"]["product_id"] for p in prods])
        # image fields filled for preview (lint would still flag the source JSON)
        rendered_img = pc["components_config"]["base"]["stack"]["components"][0]["source"]["light"]
        for k in lab_lint.IMAGE_URL_FIELDS:
            self.assertEqual(rendered_img[k], rendered_img["original"])
        self.assertTrue(any(f.rule == "image-urls" for f in lab_lint.lint(var, helpers.ui_config(), helpers.products())))
        # ui_config always present, every font alias has both faces
        ui = offerings["ui_config"]
        for alias, faces in ui["app"]["fonts"].items():
            self.assertEqual({"ios", "android"} - set(faces), set(), alias)
        self.assertNotIn("_comment", ui)
        # product mocks get a formatted price
        out = helpers.read_json(os.path.join(res, "products.json"))
        self.assertEqual(out["packages"][0]["price"]["formatted"], "$59.99")
        # local assets mirrored where both harnesses look
        for fname in ("hero.png", "bg.png"):
            self.assertTrue(os.path.isfile(os.path.join(res, "qa", "pawwalls", "assets", "lab", fname)))
        # a second render starts clean
        open(os.path.join(res, "stale.txt"), "w").close()
        with contextlib.redirect_stdout(io.StringIO()):
            self.lab.render("v")
        self.assertFalse(os.path.exists(os.path.join(res, "stale.txt")))

    def test_formatted_price(self):
        f = self.lab.formatted_price
        self.assertEqual(f({"amount": 9.99, "currency": "USD"}), "$9.99")
        self.assertEqual(f({"amount": 1234.5, "currency": "EUR"}), "€1,234.50")
        self.assertEqual(f({"amount": 9.99, "currency": "CHF"}), "9.99 CHF")
        self.assertEqual(f({"amount": 1, "currency": "USD", "formatted": "one buck"}), "one buck")

    def test_merged_ui_config_completes_font_faces_and_prefers_variation_file(self):
        self._variation("v", dsl.paywall(dsl.stack([]), dsl.Strings()))
        self.lab.save_json(os.path.join(self.home, "variations", "v", "ui_config.json"),
                           {"app": {"fonts": {"brand": {"android": {"type": "name", "value": "Roboto"}}}}})
        ui = self.lab.merged_ui_config("v")
        self.assertEqual(ui["app"]["fonts"]["brand"]["ios"], {"type": "name", "value": "Roboto"})
        self.assertNotIn("serif", ui["app"]["fonts"])   # variation file wins over my/ui_config.json
        self.assertEqual(ui["app"]["colors"], {})

    def test_relative_lab_home_resolves_absolute_and_generate_runs(self):
        # Regression: a relative PAYWALL_LAB_HOME broke `preview --generate` (cwd changes)
        # and the iOS harness (which needs an absolute resources path).
        os.chdir(self.tmp.name)
        lab = helpers.load_lab("home")
        self.assertTrue(os.path.isabs(lab.MY))
        self.assertEqual(os.path.realpath(lab.MY), os.path.realpath(self.home))   # macOS: /var -> /private/var
        self.assertTrue(os.path.isabs(lab.RES_DIR))
        d = os.path.join(self.home, "variations", "gen")
        os.makedirs(d)
        with open(os.path.join(d, "generate.py"), "w") as f:
            f.write("import os, sys\nsys.path.insert(0, os.environ['PAYWALL_LAB_ROOT'])\n"
                    "from paywall_dsl import *\nS = Strings()\n"
                    "assert os.path.isabs(lab_home()), lab_home()\n"
                    "assert len(products()) == 2\n"
                    "write(paywall(stack([text(S.add('t', 'hi'))]), S))\n")
        with contextlib.redirect_stdout(io.StringIO()):
            lab.run_generate(d)
        self.assertTrue(os.path.isfile(os.path.join(d, "paywall.json")))

    def test_new_from_variation_copies_json_and_assets(self):
        helpers.generate_fixture(self.home, "base")
        args = argparse.Namespace(name="first", source="base", paywall=None)
        with contextlib.redirect_stdout(io.StringIO()):
            self.lab.cmd_new(args)
        d = os.path.join(self.home, "variations", "first")
        for f in ("paywall.json", "NOTES.md", os.path.join("assets", "bg.png")):
            self.assertTrue(os.path.isfile(os.path.join(d, f)), f)
        self.assertTrue(os.path.isdir(os.path.join(d, "screenshots")))
        self.assertEqual(self.lab.load_variation("first"), self.lab.load_variation("base"))
        var = self.lab.load_variation("first")
        findings = lab_lint.lint(var, self.lab.merged_ui_config("first"), self.lab.products(),
                                 assets_dir=os.path.join(d, "assets"))
        self.assertEqual([], [f.rule for f in findings])
        self.assertEqual(self.lab.list_variations(), ["base", "first"])
        with self.assertRaises(SystemExit):   # refuses to overwrite
            with contextlib.redirect_stderr(io.StringIO()):
                self.lab.cmd_new(args)

    def test_working_copy_normalizes_api_components(self):
        wc = self.lab.working_copy({"components_config": {"base": {}}, "components_localizations": {"en_US": {}},
                                    "default_locale": "en_US", "revision": 7, "extra": "ignored"})
        self.assertEqual(wc, {"components_config": {"base": {}}, "components_localizations": {"en_US": {}},
                              "default_locale": "en_US", "revision": 7, "automatically_scale_font_size": True})


if __name__ == "__main__":
    unittest.main()
