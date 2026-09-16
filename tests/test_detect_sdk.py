"""`detect-sdk` from fixture app trees; harness pins round-trip; the compat matrix
in docs/platforms.md covers the pinned versions."""
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest

from tests.helpers import ROOT, read_text

import lab_platforms as lp


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class DetectSdkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_cocoapods_and_gradle(self):
        write(os.path.join(self.app, "ios", "Podfile.lock"),
              "PODS:\n  - PurchasesHybridCommon (13.0.0):\n    - RevenueCat (= 5.76.0)\n  - RevenueCat (5.76.0)\n"
              "  - RevenueCatUI (5.76.0)\n")
        write(os.path.join(self.app, "android", "app", "build.gradle.kts"),
              'dependencies {\n    implementation("com.revenuecat.purchases:purchases-ui:10.8.0")\n}\n')
        found = lp.detect_sdk(self.app)
        self.assertEqual(found["ios"], {"version": "5.76.0", "via": "ios/Podfile.lock"})
        self.assertEqual(found["android"], {"version": "10.8.0", "via": "android/app/build.gradle.kts"})

    def test_swiftpm_and_version_catalog(self):
        write(os.path.join(self.app, "App.xcodeproj", "project.xcworkspace", "xcshareddata", "swiftpm", "Package.resolved"),
              json.dumps({"pins": [{"identity": "purchases-ios", "state": {"version": "5.89.0"}}]}))
        write(os.path.join(self.app, "gradle", "libs.versions.toml"), '[versions]\nrevenuecat = "10.22.0"\n')
        found = lp.detect_sdk(self.app)
        self.assertEqual(found["ios"]["version"], "5.89.0")
        self.assertIn("Package.resolved", found["ios"]["via"])
        self.assertEqual(found["android"]["version"], "10.22.0")

    def test_react_native_goes_through_hybrid_common(self):
        write(os.path.join(self.app, "node_modules", "react-native-purchases", "android", "build.gradle"),
              "dependencies {\n    implementation 'com.revenuecat.purchases:purchases-hybrid-common:14.0.0'\n}\n")
        orig = lp._hybrid_common_to_native
        lp._hybrid_common_to_native = lambda v: {"ios": "5.50.0", "android": "9.0.0"} if v == "14.0.0" else {}
        try:
            found = lp.detect_sdk(self.app)
        finally:
            lp._hybrid_common_to_native = orig
        self.assertEqual(found["ios"], {"version": "5.50.0", "via": "react-native-purchases → purchases-hybrid-common 14.0.0"})
        self.assertEqual(found["android"]["version"], "9.0.0")

    def test_nothing_found(self):
        write(os.path.join(self.app, "README.md"), "no sdk here\n")
        self.assertEqual(lp.detect_sdk(self.app), {})

    def test_node_modules_and_build_dirs_are_skipped_for_native_files(self):
        write(os.path.join(self.app, "node_modules", "x", "Podfile.lock"), "  - RevenueCat (1.0.0)\n")
        write(os.path.join(self.app, "build", "build.gradle"), "com.revenuecat.purchases:purchases:1.0.0")
        self.assertEqual(lp.detect_sdk(self.app), {})


class PinTests(unittest.TestCase):
    def test_apply_pins_round_trips_through_current_pins(self):
        with tempfile.TemporaryDirectory() as root:
            for rel in (os.path.join(lp.IOS_PROJECT, "project.pbxproj"),
                        os.path.join(lp.ANDROID_DIR, "app", "build.gradle.kts")):
                os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(root, rel))
            with contextlib.redirect_stdout(io.StringIO()):
                lp.apply_pins(root, {"ios": {"version": "1.2.3"}, "android": {"version": "4.5.6"}})
            self.assertEqual(lp.current_pins(root), {"ios": "1.2.3", "android": "4.5.6"})
            pbx = read_text(os.path.join(root, lp.IOS_PROJECT, "project.pbxproj"))
            self.assertEqual(pbx.count("version = 1.2.3;"), 1)

    def test_repo_pins_are_in_the_compat_matrix(self):
        pins = lp.current_pins(ROOT)
        self.assertTrue(pins.get("ios") and pins.get("android"), pins)
        matrix = read_text(os.path.join(ROOT, "docs", "platforms.md"))
        ios_rows = re.findall(r"\|\s*ios\s*\|\s*purchases-ios\s+([\d.]+)\s*\|", matrix)
        android_rows = re.findall(r"\|\s*android\s*\|\s*purchases-android\s+([\d.]+)\s*\|", matrix)
        self.assertIn(pins["ios"], ios_rows, "docs/platforms.md matrix lacks the pinned purchases-ios version")
        self.assertIn(pins["android"], android_rows, "docs/platforms.md matrix lacks the pinned purchases-android version")


if __name__ == "__main__":
    unittest.main()
