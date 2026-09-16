"""Each documented lint rule fires on the shape it documents, and only then."""
import copy
import os
import tempfile
import unittest

from tests import helpers

import lab_lint
import paywall_dsl as dsl

PRODUCTS = helpers.products()
UI = helpers.ui_config()


def base_paywall():
    dsl.reset_ids()
    S = dsl.Strings()
    title = dsl.text(S.add("title", "Unlock everything"))
    cards = [dsl.package(p["identifier"], dsl.stack([dsl.text(S.add("card_" + p["identifier"], p["name"]))]))
             for p in PRODUCTS["packages"]]
    cta = dsl.purchase_button(dsl.stack([dsl.text(S.add("cta", "Continue"))]))
    return dsl.paywall(dsl.stack([title, *cards, cta]), S), S


def rules(var, assets_dir=None, ui=UI):
    return {f.rule for f in lab_lint.lint(var, ui, PRODUCTS, assets_dir=assets_dir)}


class LintRules(unittest.TestCase):
    def test_clean_paywall_has_no_findings(self):
        var, _ = base_paywall()
        self.assertEqual(rules(var), set())

    def test_default_locale(self):
        var, _ = base_paywall()
        var["default_locale"] = "fr_FR"
        self.assertIn("default-locale", rules(var))

    def test_lid_format(self):
        var, _ = base_paywall()
        var["components_localizations"]["en_US"]["free-form id"] = "x"
        self.assertIn("lid-format", rules(var))

    def test_lid_missing_and_unused(self):
        var, _ = base_paywall()
        root = var["components_config"]["base"]["stack"]
        root["components"][0]["text_lid"] = dsl.lid("never added")
        r = rules(var)
        self.assertIn("lid-missing", r)
        self.assertIn("lid-unused", r)   # the orphaned title string

    def test_lid_in_override_and_url_are_referenced(self):
        var, S = base_paywall()
        root = var["components_config"]["base"]["stack"]
        alt = S.add("title_alt", "Try it free")
        url = S.add("terms_url", "https://example.com/terms")
        root["components"][0]["overrides"] = [dsl.when(dsl.INTRO, text_lid=alt)]
        root["components"].append(dsl.button(dsl.navigate_action(url, "terms"), dsl.stack([])))
        var["components_localizations"] = S.localizations()
        self.assertNotIn("lid-unused", rules(var))

    def test_image_urls_and_size(self):
        var, _ = base_paywall()
        with tempfile.TemporaryDirectory() as assets:
            dsl.write_png(os.path.join(assets, "bg.png"), 2, 2, lambda x, y: (0, 0, 0, 255))
            img = dsl.image("bg.png", 2, 2)
            var["components_config"]["base"]["stack"]["components"].append(img)
            self.assertEqual(rules(var, assets), set())
            del img["source"]["light"]["webp"]
            img["source"]["light"]["width"] = "2"
            r = rules(var, assets)
            self.assertIn("image-urls", r)
            self.assertIn("image-size", r)

    def test_local_asset_missing(self):
        var, _ = base_paywall()
        var["components_config"]["base"]["background"] = dsl.image_background("nope.png", 10, 10)
        self.assertIn("local-asset-missing", rules(var))
        with tempfile.TemporaryDirectory() as assets:
            self.assertIn("local-asset-missing", rules(var, assets))

    def test_footer_type(self):
        var, _ = base_paywall()
        var["components_config"]["base"]["sticky_footer"] = {"type": "sticky_footer", "stack": dsl.stack([])}
        self.assertIn("footer-type", rules(var))
        var["components_config"]["base"]["sticky_footer"]["type"] = "footer"
        self.assertNotIn("footer-type", rules(var))

    def test_unknown_component_and_condition(self):
        var, _ = base_paywall()
        root = var["components_config"]["base"]["stack"]
        root["components"].append({"type": "hologram", "id": "x_001"})
        root["components"][0]["overrides"] = [dsl.when({"type": "moon_phase"}, visible=False)]
        r = rules(var)
        self.assertIn("unknown-component", r)
        self.assertIn("unknown-condition", r)

    def test_package_unknown(self):
        var, S = base_paywall()
        var["components_config"]["base"]["stack"]["components"].append(
            dsl.package("$rc_lifetime", dsl.stack([dsl.text(S.add("life", "Lifetime"))])))
        var["components_localizations"] = S.localizations()
        self.assertIn("package-unknown", rules(var))

    def test_nested_visibility_rule_inside_tabs(self):
        var, S = base_paywall()
        hidden = dsl.text(S.add("only_trial", "Then $9.99"), overrides=dsl.show_when_intro(), visible=False)
        toggle = dsl.trial_toggle([dsl.tab_control()], [dsl.tab_control(), hidden], track_on="#FF0000ff")
        var["components_config"]["base"]["stack"]["components"].append(toggle)
        var["components_localizations"] = S.localizations()
        r = rules(var)
        self.assertIn("nested-visibility-rule", r)
        self.assertNotIn("unknown-component", r)   # tabs/tab/tab_control/tab_control_toggle are known

    def test_font_alias(self):
        var, _ = base_paywall()
        root = var["components_config"]["base"]["stack"]
        root["components"][0]["font_name"] = "serif"
        self.assertNotIn("font-alias", rules(var))
        root["components"][0]["font_name"] = "comic"
        self.assertIn("font-alias", rules(var))
        one_face = copy.deepcopy(UI)
        one_face["app"]["fonts"]["comic"] = {"ios": {"type": "name", "value": "Comic"}}
        self.assertIn("font-alias", rules(var, ui=one_face))

    def test_trial_copy_unconditional(self):
        var, S = base_paywall()
        root = var["components_config"]["base"]["stack"]
        root["components"][0]["text_lid"] = S.add("title", "Start your free trial")
        var["components_localizations"] = S.localizations()
        self.assertIn("trial-copy-unconditional", rules(var))
        # any intro-offer rule anywhere silences it (the recipe way)
        plain = dsl.text(S.add("title_plain", "Unlock everything"))
        dsl.eligibility_siblings(root["components"][0], plain)
        root["components"].insert(1, plain)
        var["components_localizations"] = S.localizations()
        self.assertNotIn("trial-copy-unconditional", rules(var))


if __name__ == "__main__":
    unittest.main()
