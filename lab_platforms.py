"""Platform drivers for rc-paywall-lab: toolchain discovery (`doctor`), SDK version
detection (`detect-sdk`), and preview on the iOS simulator / Android emulator.

Both harnesses take the same inputs — a rendered resources dir and an eligibility
flag — and produce the same screenshots. iOS reads the resources dir directly
(simulator processes see the host filesystem); Android fetches them from a tiny
loopback HTTP server (the emulator reaches the host at 10.0.2.2).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BUNDLE_ID = "dev.paywalllab.harness"
IOS_SCHEME = "PaywallLabHarness"
IOS_PROJECT = os.path.join("harness", "ios", "PaywallLabHarness.xcodeproj")
ANDROID_DIR = os.path.join("harness", "android")
ANDROID_ACTIVITY = f"{BUNDLE_ID}/.MainActivity"
STATE_FLAG = {"eligible": True, "trial-used": False}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def build_root(root):
    return os.path.join(root, ".build")


# ------------------------------------------------------------------ toolchain discovery
def android_home(cfg=None):
    cands = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
             (cfg or {}).get("android", {}).get("sdk_dir"),
             os.path.expanduser("~/Library/Android/sdk"), os.path.expanduser("~/Android/Sdk")]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "platform-tools")):
            return c
    return None


def java_major(java_bin):
    r = run([java_bin, "-version"])
    m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
    if not m:
        return None
    major = int(m.group(1))
    return int(m.group(2)) if major == 1 and m.group(2) else major


def java_home(cfg=None):
    """First JDK >= 17 among: config, $JAVA_HOME, /usr/libexec/java_home, Homebrew, Android Studio."""
    cands = [(cfg or {}).get("android", {}).get("java_home"), os.environ.get("JAVA_HOME")]
    if sys.platform == "darwin" and os.path.exists("/usr/libexec/java_home"):
        r = run(["/usr/libexec/java_home", "-v", "17+"])
        if r.returncode == 0:
            cands.append(r.stdout.strip())
    cands += ["/opt/homebrew/opt/openjdk@21", "/opt/homebrew/opt/openjdk@17", "/opt/homebrew/opt/openjdk",
              "/usr/local/opt/openjdk@21", "/usr/local/opt/openjdk@17", "/usr/local/opt/openjdk",
              "/Applications/Android Studio.app/Contents/jbr/Contents/Home",
              os.path.expanduser("~/Applications/Android Studio.app/Contents/jbr/Contents/Home")]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "bin", "java")):
            v = java_major(os.path.join(c, "bin", "java"))
            if v and v >= 17:
                return c
    return None


def sim_udid(device_name, boot=True):
    r = run(["xcrun", "simctl", "list", "devices", "available", "--json"])
    if r.returncode != 0:
        return None
    devices = json.loads(r.stdout)["devices"]
    best = None
    for runtime, devs in sorted(devices.items(), reverse=True):
        if "iOS" not in runtime:
            continue
        for d in devs:
            if d["name"] == device_name:
                if d["state"] == "Booted":
                    return d["udid"]
                best = best or d["udid"]
    if best and boot:
        run(["xcrun", "simctl", "boot", best])
        run(["open", "-a", "Simulator"])
        time.sleep(8)
    return best


def list_avds(home):
    emu = os.path.join(home, "emulator", "emulator")
    if not os.path.isfile(emu):
        return []
    return [l.strip() for l in run([emu, "-list-avds"]).stdout.splitlines()
            if l.strip() and not l.startswith("INFO")]


# ------------------------------------------------------------------ doctor
def doctor(cfg, my, root, as_json=False):
    checks = []

    def add(name, ok, detail="", fix=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail, "fix": fix})

    add("python >= 3.9", sys.version_info >= (3, 9), sys.version.split()[0])
    add("my/config.json", cfg is not None, "" if cfg else "missing",
        "python3 lab.py init --project <proj_id>")
    key_var = (cfg or {}).get("api_key_env_var", "RC_API_V2_KEY")
    env_file = os.path.join(my, ".env")
    has_key = bool(os.environ.get(key_var)) or (os.path.isfile(env_file) and key_var in open(env_file).read())
    add("RevenueCat API key", has_key, key_var, f"export {key_var}=sk_... or add it to my/.env")
    prods = os.path.join(my, "products.json")
    if os.path.isfile(prods):
        pk = json.load(open(prods)).get("packages", [])
        unpriced = [p["identifier"] for p in pk if not p.get("price", {}).get("amount")]
        add("my/products.json prices", pk and not unpriced,
            f"{len(pk)} package(s)" + (f", unpriced: {', '.join(unpriced)}" if unpriced else ""),
            "edit my/products.json — price/period/trial per package")
    else:
        add("my/products.json", False, "missing", "cp my/products.example.json my/products.json and edit")

    platforms = (cfg or {}).get("platforms", ["ios", "android"])
    if "ios" in platforms:
        xc = run(["xcode-select", "-p"])
        add("Xcode", xc.returncode == 0, xc.stdout.strip(), "install Xcode + `xcode-select --install`")
        name = (cfg or {}).get("ios", {}).get("device_name", "iPhone 17 Pro")
        udid = sim_udid(name, boot=False) if xc.returncode == 0 else None
        add(f"iOS simulator '{name}'", bool(udid), udid or "not found",
            "create one in Xcode → Devices, or set ios.device_name in my/config.json")
        app = os.path.join(build_root(root), "ios", "Build", "Products", "Debug-iphonesimulator", IOS_SCHEME + ".app")
        add("iOS harness built", os.path.isdir(app), "" if os.path.isdir(app) else "not yet",
            "python3 lab.py preview <variation> --platform ios  (first build resolves purchases-ios: ~10 min)")
    if "android" in platforms:
        jh = java_home(cfg)
        add("JDK >= 17", bool(jh), jh or "none found", "brew install openjdk@21 (or set android.java_home)")
        home = android_home(cfg)
        add("Android SDK", bool(home), home or "not found", "install Android Studio or set ANDROID_HOME")
        if home:
            add("adb", os.path.isfile(os.path.join(home, "platform-tools", "adb")), "", "SDK Manager → Platform-Tools")
            add("emulator", os.path.isfile(os.path.join(home, "emulator", "emulator")), "", "SDK Manager → Android Emulator")
            avds = list_avds(home)
            want = (cfg or {}).get("android", {}).get("avd")
            add("Android AVD", bool(avds) and (not want or want in avds), ", ".join(avds) or "none",
                "create one in Android Studio → Device Manager, then set android.avd in my/config.json")
        apk = os.path.join(root, ANDROID_DIR, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
        add("Android harness built", os.path.isfile(apk), "" if os.path.isfile(apk) else "not yet",
            "python3 lab.py preview <variation> --platform android  (first build downloads Gradle+deps: ~5 min)")
    add("gh CLI (optional, for `suggest --open`)", bool(shutil.which("gh")), "", "brew install gh")

    if as_json:
        print(json.dumps(checks, indent=2))
    else:
        for c in checks:
            mark = "✅" if c["ok"] else "❌"
            line = f"{mark} {c['check']}"
            if c["detail"]:
                line += f"  — {c['detail']}"
            print(line)
            if not c["ok"] and c["fix"]:
                print(f"      fix: {c['fix']}")
    bad = [c for c in checks if not c["ok"] and "optional" not in c["check"]]
    print(f"\n{'all good' if not bad else str(len(bad)) + ' problem(s)'}")
    return not bad


# ------------------------------------------------------------------ detect-sdk
def _find(app_dir, names, maxdepth=3):
    out = []
    for dirpath, dirs, files in os.walk(app_dir):
        depth = dirpath[len(app_dir):].count(os.sep)
        dirs[:] = [d for d in dirs if d not in ("node_modules", "build", ".git", "Pods", "DerivedData", ".build")
                   and depth < maxdepth]
        for n in names:
            if n in files:
                out.append(os.path.join(dirpath, n))
    return out


def _fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read().decode()
    except Exception:
        return ""


def _hybrid_common_to_native(hc_version):
    """purchases-hybrid-common <ver> pins both native SDKs; read them from its podspec + Maven POM."""
    found = {}
    pod = _fetch(f"https://raw.githubusercontent.com/RevenueCat/purchases-hybrid-common/{hc_version}/PurchasesHybridCommon.podspec")
    m = re.search(r"s\.dependency\s+'RevenueCat',\s*'([\d.]+)'", pod)
    if m:
        found["ios"] = m.group(1)
    pom = _fetch(f"https://repo1.maven.org/maven2/com/revenuecat/purchases/purchases-hybrid-common/{hc_version}/purchases-hybrid-common-{hc_version}.pom")
    m = re.search(r"<artifactId>purchases</artifactId>\s*<version>([\d.]+)</version>", pom)
    if m:
        found["android"] = m.group(1)
    return found


def detect_sdk(app_dir):
    found = {}
    for f in _find(app_dir, ["Podfile.lock"]):
        m = re.search(r"^\s+- RevenueCat \(([\d.]+)\)", open(f).read(), re.M)
        if m:
            found.setdefault("ios", {"version": m.group(1), "via": os.path.relpath(f, app_dir)})
    for f in _find(app_dir, ["Package.resolved"], maxdepth=4):
        try:
            for pin in json.load(open(f)).get("pins", []):
                if pin.get("identity") == "purchases-ios":
                    found.setdefault("ios", {"version": pin["state"]["version"], "via": os.path.relpath(f, app_dir)})
        except Exception:
            pass
    for f in _find(app_dir, ["build.gradle", "build.gradle.kts", "libs.versions.toml"], maxdepth=4):
        txt = open(f).read()
        m = re.search(r"com\.revenuecat\.purchases:purchases(?:-ui)?:([\d.]+)", txt) or \
            re.search(r"revenuecat\w*\s*=\s*\"([\d.]+)\"", txt, re.I)
        if m and "hybrid-common" not in m.group(0):
            found.setdefault("android", {"version": m.group(1), "via": os.path.relpath(f, app_dir)})
    # React Native / Flutter: go through purchases-hybrid-common
    hc = None
    rn = os.path.join(app_dir, "node_modules", "react-native-purchases", "android", "build.gradle")
    if os.path.isfile(rn):
        m = re.search(r"purchases-hybrid-common:([\d.]+)", open(rn).read())
        hc = (m.group(1), "react-native-purchases") if m else None
    lock = os.path.join(app_dir, "pubspec.lock")
    if not hc and os.path.isfile(lock):
        m = re.search(r"purchases_flutter:\n(?:.*\n){1,4}?\s+version: \"([\d.]+)\"", open(lock).read())
        if m:
            g = os.path.expanduser(f"~/.pub-cache/hosted/pub.dev/purchases_flutter-{m.group(1)}/android/build.gradle")
            if os.path.isfile(g):
                m2 = re.search(r"purchases-hybrid-common:([\d.]+)", open(g).read())
                hc = (m2.group(1), "purchases_flutter") if m2 else None
    if hc:
        for plat, ver in _hybrid_common_to_native(hc[0]).items():
            found.setdefault(plat, {"version": ver, "via": f"{hc[1]} → purchases-hybrid-common {hc[0]}"})
    return found


def apply_pins(root, found):
    if "ios" in found:
        p = os.path.join(root, IOS_PROJECT, "project.pbxproj")
        s = open(p).read()
        s2 = re.sub(r"(kind = exactVersion;\s*version = )[\d.]+;", rf"\g<1>{found['ios']['version']};", s)
        open(p, "w").write(s2)
        print(f"ios harness pinned to purchases-ios {found['ios']['version']}")
    if "android" in found:
        p = os.path.join(root, ANDROID_DIR, "app", "build.gradle.kts")
        s = open(p).read()
        s2 = re.sub(r'val revenueCatVersion = "[\d.]+"', f'val revenueCatVersion = "{found["android"]["version"]}"', s)
        open(p, "w").write(s2)
        print(f"android harness pinned to purchases-android {found['android']['version']}")


def current_pins(root):
    pins = {}
    p = os.path.join(root, IOS_PROJECT, "project.pbxproj")
    if os.path.isfile(p):
        m = re.search(r"kind = exactVersion;\s*version = ([\d.]+);", open(p).read())
        pins["ios"] = m.group(1) if m else None
    p = os.path.join(root, ANDROID_DIR, "app", "build.gradle.kts")
    if os.path.isfile(p):
        m = re.search(r'val revenueCatVersion = "([\d.]+)"', open(p).read())
        pins["android"] = m.group(1) if m else None
    return pins


# ------------------------------------------------------------------ iOS
def build_ios(root, udid):
    print("building iOS harness (first time: resolves purchases-ios from GitHub — a ~1 GB clone, "
          "~10 min, cached afterwards)…")
    r = run(["xcodebuild", "-project", os.path.join(root, IOS_PROJECT), "-scheme", IOS_SCHEME,
             "-configuration", "Debug", "-destination", f"platform=iOS Simulator,id={udid}",
             "-derivedDataPath", os.path.join(build_root(root), "ios"), "build"])
    if "BUILD SUCCEEDED" not in r.stdout:
        errs = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "error:" in l)
        raise SystemExit("iOS build failed:\n" + (errs or (r.stdout + r.stderr)[-3000:]))
    print("iOS build succeeded")


def preview_ios(cfg, root, res_dir, shots_dir, build=False, states="eligible,trial-used"):
    ios = cfg.get("ios", {})
    udid = sim_udid(ios.get("device_name", "iPhone 17 Pro"))
    if not udid:
        raise SystemExit(f"no simulator named '{ios.get('device_name')}' — see `lab.py doctor`")
    app = os.path.join(build_root(root), "ios", "Build", "Products", "Debug-iphonesimulator", IOS_SCHEME + ".app")
    if build or not os.path.isdir(app):
        build_ios(root, udid)
    run(["xcrun", "simctl", "install", udid, app])
    out = []
    for state in [s.strip() for s in states.split(",") if s.strip()]:
        run(["xcrun", "simctl", "terminate", udid, BUNDLE_ID])
        env = {**os.environ,
               "SIMCTL_CHILD_PAYWALL_LAB_RESOURCES": res_dir,
               "SIMCTL_CHILD_PAYWALL_LAB_ELIGIBLE": "1" if STATE_FLAG.get(state, True) else "0",
               "SIMCTL_CHILD_PAYWALL_LAB_CONTROLS": "0"}
        subprocess.run(["xcrun", "simctl", "launch", udid, BUNDLE_ID], env=env, capture_output=True)
        time.sleep(ios.get("settle_seconds", 7))
        shot = os.path.join(shots_dir, f"ios-{state}.png")
        run(["xcrun", "simctl", "io", udid, "screenshot", shot])
        print(f"captured {os.path.relpath(shot, root)}")
        out.append(shot)
    return out


# ------------------------------------------------------------------ Android
class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory, port):
    handler = lambda *a, **k: _QuietHandler(*a, directory=directory, **k)  # noqa: E731
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def adb_path(home):
    return os.path.join(home, "platform-tools", "adb")


def ensure_emulator(cfg, home):
    adb = adb_path(home)
    run([adb, "start-server"])
    devs = [l.split()[0] for l in run([adb, "devices"]).stdout.splitlines()[1:] if l.strip().endswith("device")]
    if devs:
        return devs[0]
    android = cfg.get("android", {})
    avd = android.get("avd") or (list_avds(home) or [None])[0]
    if not avd:
        raise SystemExit("no Android AVD found — create one in Android Studio → Device Manager")
    # -no-snapshot-load: a stale snapshot leaves the device 'offline' forever; a cold boot is reliable.
    cmd = [os.path.join(home, "emulator", "emulator"), "-avd", avd, "-no-snapshot-load", "-no-boot-anim"]
    if android.get("headless", True):
        cmd += ["-no-window", "-no-audio", "-gpu", "swiftshader_indirect"]
    print(f"booting emulator '{avd}' (cold boot, ~1 min)…")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.time() + 300
    while time.time() < deadline:
        devs = [l.split()[0] for l in run([adb, "devices"]).stdout.splitlines()[1:] if l.strip().endswith("device")]
        if devs and run([adb, "-s", devs[0], "shell", "getprop", "sys.boot_completed"]).stdout.strip() == "1":
            return devs[0]
        time.sleep(5)
    raise SystemExit("emulator did not finish booting in 5 minutes")


def build_android(root, cfg, home):
    d = os.path.join(root, ANDROID_DIR)
    jh = java_home(cfg)
    if not jh:
        raise SystemExit("no JDK >= 17 found — brew install openjdk@21 or set android.java_home in my/config.json")
    with open(os.path.join(d, "local.properties"), "w") as f:
        f.write(f"sdk.dir={home}\n")
    print("building Android harness (first time downloads Gradle + dependencies, ~5 min)…")
    r = run(["./gradlew", ":app:assembleDebug", "-q", "--console=plain"], cwd=d,
            env={**os.environ, "JAVA_HOME": jh, "ANDROID_HOME": home})
    if r.returncode != 0:
        raise SystemExit("Android build failed:\n" + (r.stderr + r.stdout)[-4000:])
    print("Android build succeeded")


def preview_android(cfg, root, res_dir, shots_dir, build=False, states="eligible,trial-used"):
    home = android_home(cfg)
    if not home:
        raise SystemExit("Android SDK not found — see `lab.py doctor`")
    android = cfg.get("android", {})
    apk = os.path.join(root, ANDROID_DIR, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
    if build or not os.path.isfile(apk):
        build_android(root, cfg, home)
    serial = ensure_emulator(cfg, home)
    adb = [adb_path(home), "-s", serial]
    port = int(android.get("port", 8765))
    srv = serve(res_dir, port)
    try:
        r = run(adb + ["install", "-r", apk])
        if "Success" not in r.stdout:
            raise SystemExit("adb install failed: " + r.stdout + r.stderr)
        # Local asset URLs are identical across renders, so the app's image cache would
        # happily serve last run's picture. Clear app data before each preview.
        run(adb + ["shell", "pm", "clear", BUNDLE_ID])
        out = []
        for state in [s.strip() for s in states.split(",") if s.strip()]:
            run(adb + ["shell", "am", "force-stop", BUNDLE_ID])
            run(adb + ["shell", "am", "start", "-W", "-n", ANDROID_ACTIVITY,
                       "--ez", "eligible", "true" if STATE_FLAG.get(state, True) else "false",
                       "--ez", "controls", "false", "--es", "resources", f"http://10.0.2.2:{port}/"])
            time.sleep(android.get("settle_seconds", 9))
            shot = os.path.join(shots_dir, f"android-{state}.png")
            png = subprocess.run(adb + ["exec-out", "screencap", "-p"], capture_output=True).stdout
            with open(shot, "wb") as f:
                f.write(png)
            print(f"captured {os.path.relpath(shot, root)}")
            out.append(shot)
        return out
    finally:
        srv.shutdown()
