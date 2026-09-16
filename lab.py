#!/usr/bin/env python3
"""rc-paywall-lab — author, preview, lint, and ship RevenueCat Paywalls v2
(components) as JSON, driven by a coding agent. No dashboard builder needed.

Everything user-specific lives in `my/` (or $PAYWALL_LAB_HOME): config.json,
products.json, ui_config.json, variations/, snapshots/. Secrets come from the
environment or `my/.env`. Zero Python dependencies (stdlib only).

Commands (run `python3 lab.py <cmd> -h` for details):

  doctor                     Check toolchains, simulators, API key; print fixes.
  detect-sdk [APP_DIR]       Find the RevenueCat SDK versions an app ships
                             (native iOS/Android, React Native, Flutter) and
                             optionally pin both harnesses to them (--apply).
  init --project PROJ_ID     Discover paywalls/offerings/products via the API
                             and write my/config.json + my/products.json.
  status                     Live paywall state (draft vs published revisions)
                             + local variations.
  pull [--paywall KEY]       Snapshot live config into my/snapshots/.
  new NAME [--source ...]    Start a variation from published/draft/another
                             variation/a library design.
  render NAME                Emit simulator resources for a variation.
  preview NAME [--platform]  Render + screenshot on iOS simulator and/or
                             Android emulator in BOTH eligibility states.
  diff NAME                  Path-by-path diff of a variation vs live.
  lint NAME                  Validate against every API/SDK rule we know.
  upload-assets NAME         Push local images to RevenueCat's media library.
  push NAME --yes            Upload as the RevenueCat DRAFT (not user-visible).
  create NAME --title T      Create a brand-new paywall (unpublished draft).
  publish --confirm PUBLISH  Make the draft live. Human approval required.
  suggest                    Draft an upstream "prompt" (issue) describing an
                             improvement you made locally.
"""
import argparse
import base64
import datetime
import difflib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
MY = os.path.abspath(os.environ.get("PAYWALL_LAB_HOME") or os.path.join(ROOT, "my"))
CONFIG_PATH = os.path.join(MY, "config.json")
PRODUCTS_PATH = os.path.join(MY, "products.json")
UI_CONFIG_PATH = os.path.join(MY, "ui_config.json")
ENV_PATH = os.path.join(MY, ".env")
VAR_DIR = os.path.join(MY, "variations")
SNAP_DIR = os.path.join(MY, "snapshots")
RES_DIR = os.path.join(MY, ".resources")
LIBRARY_DESIGNS = os.path.join(ROOT, "library", "designs")
LOCAL_ASSET_BASE = "https://assets.pawwalls.com/lab/"   # rewritten by the harnesses
IMAGE_URL_FIELDS = ("original", "heic", "heic_low_res", "webp", "webp_low_res")

sys.path.insert(0, ROOT)
import lab_platforms  # noqa: E402
import lab_lint  # noqa: E402


# ---------------------------------------------------------------- utilities
def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def note(msg):
    print(f"note: {msg}")


def load_json(path, default=None):
    if not os.path.isfile(path):
        if default is not None:
            return default
        die(f"missing {os.path.relpath(path, ROOT)} — run `python3 lab.py init` "
            f"(or copy the .example file next to it)")
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def config():
    return load_json(CONFIG_PATH)


def products():
    return load_json(PRODUCTS_PATH)


def api_key(cfg=None):
    cfg = cfg or config()
    var = cfg.get("api_key_env_var", "RC_API_V2_KEY")
    key = os.environ.get(var)
    if key:
        return key
    if os.path.isfile(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line.startswith(var + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    die(f"no API key: export {var}=... or put {var}=... in {os.path.relpath(ENV_PATH, ROOT)}\n"
        f"(RevenueCat → Project settings → API keys → secret key with paywall/offering write scopes)")


def api(method, path, body=None, cfg=None, project_scoped=True):
    cfg = cfg or config()
    base = cfg.get("api_base", "https://api.revenuecat.com/v2")
    url = f"{base}/projects/{cfg['project_id']}{path}" if project_scoped else f"{base}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {api_key(cfg)}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        die(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:4000]}")


def api_list(path, cfg=None):
    """Follow RevenueCat v2 pagination (`items` + `next_page`)."""
    items, nxt = [], path
    while nxt:
        page = api("GET", nxt.replace(f"/projects/{(cfg or config())['project_id']}", "", 1)
                   if nxt.startswith("/projects/") else nxt, cfg=cfg)
        items += page.get("items", [])
        nxt = page.get("next_page")
        if nxt and nxt.startswith("http"):
            nxt = nxt.split("/v2", 1)[1]
    return items


def paywall_cfg(cfg, key):
    key = key or cfg.get("default_paywall")
    if not key or key not in cfg.get("paywalls", {}):
        die(f"unknown paywall '{key}'; known: {', '.join(cfg.get('paywalls', {})) or '(none — run init)'}")
    return key, cfg["paywalls"][key]


def fetch_paywall(cfg, key):
    key, pw = paywall_cfg(cfg, key)
    return key, pw, api("GET", f"/paywalls/{pw['id']}?expand=components", cfg=cfg)


def working_copy(components):
    """Normalize a components.draft/.published object to our paywall.json shape."""
    return {
        "components_config": components["components_config"],
        "components_localizations": components["components_localizations"],
        "default_locale": components["default_locale"],
        "revision": components["revision"],
        "automatically_scale_font_size": components.get("automatically_scale_font_size", True),
    }


def variation_path(name):
    p = os.path.join(VAR_DIR, name)
    if not os.path.isdir(p):
        die(f"no variation '{name}'. Existing: {', '.join(list_variations()) or '(none)'}")
    return p


def load_variation(name):
    return load_json(os.path.join(variation_path(name), "paywall.json"))


def list_variations():
    if not os.path.isdir(VAR_DIR):
        return []
    return sorted(d for d in os.listdir(VAR_DIR)
                  if os.path.isfile(os.path.join(VAR_DIR, d, "paywall.json")))


def list_designs():
    if not os.path.isdir(LIBRARY_DESIGNS):
        return []
    return sorted(d for d in os.listdir(LIBRARY_DESIGNS)
                  if os.path.isfile(os.path.join(LIBRARY_DESIGNS, d, "generate.py")))


def walk(node, fn):
    """Depth-first visit of every dict in a JSON tree; fn(dict) may mutate."""
    if isinstance(node, dict):
        fn(node)
        for v in list(node.values()):
            walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            walk(v, fn)


# ---------------------------------------------------------------- doctor / detect-sdk / init
def cmd_doctor(args):
    ok = lab_platforms.doctor(config_or_none(), MY, ROOT, as_json=args.json)
    sys.exit(0 if ok else 1)


def config_or_none():
    return load_json(CONFIG_PATH) if os.path.isfile(CONFIG_PATH) else None


def cmd_detect_sdk(args):
    found = lab_platforms.detect_sdk(os.path.abspath(args.app_dir))
    if not found:
        die("no RevenueCat dependency found (looked for Podfile.lock, Package.resolved, "
            "package.json/react-native-purchases, pubspec.lock/purchases_flutter, Gradle files)")
    for plat, info in found.items():
        print(f"{plat}: {info['version']}   (via {info['via']})")
    if args.apply:
        lab_platforms.apply_pins(ROOT, found)
        print("pinned harnesses; rebuild with: python3 lab.py preview <name> --build")
    else:
        print("re-run with --apply to pin harness/ios and harness/android to these versions")


def _iso_period(iso):
    """'P1Y' / 'P3M' / 'P1W' / 'P7D' -> {"unit", "count"} (None for empty)."""
    m = re.match(r"^P(\d+)([YMWD])$", iso or "")
    if not m:
        return None
    return {"unit": {"Y": "year", "M": "month", "W": "week", "D": "day"}[m.group(2)], "count": int(m.group(1))}


def cmd_init(args):
    cfg = config_or_none() or {}
    project = args.project or cfg.get("project_id")
    if not project or "REPLACE" in project:
        die("--project PROJ_ID required (RevenueCat → Project settings → General → Project ID, e.g. proj1a2b3c4d)")
    example = load_json(os.path.join(MY, "config.example.json"), default={})
    example.pop("_comment", None)
    cfg = {**example, **cfg, "project_id": project}
    # drop placeholder registry entries from the example
    cfg["paywalls"] = {k: v for k, v in cfg.get("paywalls", {}).items() if "REPLACE" not in (v.get("id") or "")}
    if "REPLACE" in (cfg.get("default_paywall") or "") or cfg.get("default_paywall") not in cfg["paywalls"]:
        cfg.pop("default_paywall", None)
    save_json(CONFIG_PATH, cfg)   # so api() can read it
    print(f"project {project}")

    offerings = {o["id"]: o for o in api_list("/offerings", cfg)}
    current = next((o for o in offerings.values() if o.get("is_current")), None)
    reg = cfg["paywalls"]
    for pw in api_list("/paywalls", cfg):
        if any(v["id"] == pw["id"] for v in reg.values()):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", pw.get("name", pw["id"]).lower()).strip("-") or pw["id"]
        off = offerings.get(pw.get("offering_id") or "")
        label = pw.get("name", "") + (f" (offering: {off['lookup_key']}{' — CURRENT' if off.get('is_current') else ''})"
                                     if off else " (no offering)")
        reg[slug] = {"id": pw["id"], "label": label, "offering_id": pw.get("offering_id")}
        print(f"  paywall [{slug}] {pw['id']} — {label}")
    if reg and not cfg.get("default_paywall"):
        cfg["default_paywall"] = next((s for s, v in reg.items() if current and v.get("offering_id") == current["id"]),
                                      next(iter(reg)))
    save_json(CONFIG_PATH, cfg)

    if not os.path.isfile(PRODUCTS_PATH):
        apps = {a["id"]: a for a in api_list("/apps", cfg)}
        plat_of = {"app_store": "ios", "play_store": "android", "amazon": "amazon", "mac_app_store": "mac"}
        skel = {"_comment": "Generated by `lab.py init` from your CURRENT offering. Periods/trials/product ids come "
                            "from RevenueCat; PRICES DO NOT (the API doesn't know store prices) — fill price.amount "
                            "per package. trial = null for products without a free trial.",
                "packages": []}
        if current:
            for pk in api_list(f"/offerings/{current['id']}/packages?expand=items.product", cfg):
                entry = {"identifier": pk.get("lookup_key") or pk["id"], "name": pk.get("display_name") or pk.get("lookup_key", ""),
                         "price": {"amount": 0.0, "currency": "USD"}, "period": None, "trial": None}
                for it in (pk.get("products") or {}).get("items", []):
                    prod = it.get("product") or {}
                    plat = plat_of.get(apps.get(prod.get("app_id"), {}).get("type"), "other")
                    entry[plat] = {"product_id": prod.get("store_identifier")}
                    sub = prod.get("subscription") or {}
                    entry["period"] = entry["period"] or _iso_period(sub.get("duration"))
                    entry["trial"] = entry["trial"] or _iso_period(sub.get("trial_duration"))
                entry["period"] = entry["period"] or {"unit": "month", "count": 1}
                skel["packages"].append(entry)
            print(f"  current offering: {current['lookup_key']} — {len(skel['packages'])} package(s)")
        if not skel["packages"]:
            skel = load_json(os.path.join(MY, "products.example.json"))
            print("  (no current offering found — wrote the example products; edit them)")
        save_json(PRODUCTS_PATH, skel)
        print(f"wrote {os.path.relpath(PRODUCTS_PATH, ROOT)} — EDIT price.amount for each package before previewing")
    print(f"wrote {os.path.relpath(CONFIG_PATH, ROOT)}. Next: python3 lab.py doctor ; python3 lab.py status")


# ---------------------------------------------------------------- status / pull / new
def cmd_status(args):
    cfg = config()
    for key in cfg.get("paywalls", {}):
        _, pw, data = fetch_paywall(cfg, key)
        comps = data["components"]
        draft, pub = comps.get("draft"), comps.get("published")
        line = f"[{key}] {data['name']} (id {data['id']})"
        line += f"\n    published: revision {pub['revision']}" if pub else "\n    published: never"
        if draft is None:
            line += "\n    draft:     none (draft == published)"
        else:
            same = pub and json.dumps(draft["components_config"], sort_keys=True) == \
                json.dumps(pub["components_config"], sort_keys=True)
            line += f"\n    draft:     revision {draft['revision']}" + \
                (" (config identical to published)" if same else "  << UNPUBLISHED CHANGES")
        print(line)
    print("\nlocal variations:")
    for v in list_variations() or ["  (none)"]:
        notes = os.path.join(VAR_DIR, v, "NOTES.md")
        first = ""
        if os.path.isfile(notes):
            for ln in open(notes):
                if ln.strip() and not ln.startswith("#"):
                    first = " — " + ln.strip()[:80]
                    break
        print(f"  {v}{first}")
    print("\nlibrary designs: " + (", ".join(list_designs()) or "(none)"))


def cmd_pull(args):
    cfg = config()
    key, pw, data = fetch_paywall(cfg, args.paywall)
    os.makedirs(SNAP_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(SNAP_DIR, f"{ts}-{key}.json")
    save_json(path, data)
    comps = data["components"]
    print(f"saved {os.path.relpath(path, ROOT)}")
    print(f"published revision: {comps['published']['revision'] if comps.get('published') else '-'}")
    print(f"draft:              {'none' if comps.get('draft') is None else 'revision ' + str(comps['draft']['revision'])}")


NOTES_TEMPLATE = """# {name}

(one-line description of the change)

## Status
- [ ] previewed on iOS (both eligibility states)
- [ ] previewed on Android (both eligibility states)
- [ ] lint clean (`lab.py lint {name}`)
- [ ] approved by: <reviewer(s)>
- [ ] assets uploaded (`lab.py upload-assets`) — only if assets/ is used
- [ ] pushed to RevenueCat draft
- [ ] published (date, revision, who approved)

## Decisions / feedback

"""


def cmd_new(args):
    os.makedirs(VAR_DIR, exist_ok=True)
    dest = os.path.join(VAR_DIR, args.name)
    if os.path.exists(dest):
        die(f"variation '{args.name}' already exists")
    src = args.source
    if src in ("published", "draft"):
        cfg = config()
        _, _, data = fetch_paywall(cfg, args.paywall)
        comps = data["components"]
        payload = working_copy(comps.get(src) or comps["published"])
        os.makedirs(os.path.join(dest, "screenshots"))
        save_json(os.path.join(dest, "paywall.json"), payload)
    elif src in list_designs():
        shutil.copytree(os.path.join(LIBRARY_DESIGNS, src), dest,
                        ignore=shutil.ignore_patterns("screenshots", "README.md", "__pycache__"))
        os.makedirs(os.path.join(dest, "screenshots"), exist_ok=True)
        print(f"copied library design '{src}' → edit generate.py, then: python3 {os.path.relpath(dest, ROOT)}/generate.py")
        # Generate once so paywall.json exists against this user's products.
        run_generate(dest)
    else:
        payload = load_variation(src)
        os.makedirs(os.path.join(dest, "screenshots"))
        save_json(os.path.join(dest, "paywall.json"), payload)
        assets = os.path.join(variation_path(src), "assets")
        if os.path.isdir(assets):
            shutil.copytree(assets, os.path.join(dest, "assets"))
    with open(os.path.join(dest, "NOTES.md"), "w") as f:
        f.write(NOTES_TEMPLATE.format(name=args.name))
    print(f"created my/variations/{args.name}/ (from {src})")
    print(f"next: edit paywall.json (or generate.py), then: python3 lab.py preview {args.name}")


def run_generate(var_dir):
    import subprocess
    gen = os.path.join(var_dir, "generate.py")
    if os.path.isfile(gen):
        env = {**os.environ, "PAYWALL_LAB_ROOT": ROOT, "PAYWALL_LAB_HOME": MY}
        r = subprocess.run([sys.executable, gen], cwd=var_dir, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            die(f"generate.py failed:\n{r.stdout}\n{r.stderr}")
        print(r.stdout.strip())


# ---------------------------------------------------------------- render / preview
def formatted_price(price):
    if price.get("formatted"):
        return price["formatted"]
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "CA$", "AUD": "A$"}.get(price.get("currency", "USD"))
    amount = price.get("amount", 0)
    return f"{sym}{amount:,.2f}" if sym else f"{amount:,.2f} {price.get('currency', '')}".strip()


def complete_image_urls(components_config):
    """Both SDKs decode image sources; Android *requires* webp + webp_low_res, the
    API requires all five. Fill gaps from `original` for local preview only."""
    filled = 0

    def fix(d):
        nonlocal filled
        if "original" in d and isinstance(d.get("original"), str):
            for k in IMAGE_URL_FIELDS:
                if not d.get(k):
                    d[k] = d["original"]
                    filled += 1
    walk(components_config, fix)
    return filled


def merged_ui_config(name):
    for candidate in (os.path.join(variation_path(name), "ui_config.json"), UI_CONFIG_PATH):
        if os.path.isfile(candidate):
            ui = load_json(candidate)
            ui.pop("_comment", None)
            break
    else:
        ui = {}
    fonts = ui.setdefault("app", {}).setdefault("fonts", {})
    ui["app"].setdefault("colors", {})
    for alias, entry in fonts.items():   # each platform's decoder needs its own face
        if "ios" in entry and "android" not in entry:
            entry["android"] = {"type": "name", "value": entry["ios"].get("value", alias)}
        if "android" in entry and "ios" not in entry:
            entry["ios"] = {"type": "name", "value": entry["android"].get("value", alias)}
    return ui


def render(name, quiet=False):
    var = load_variation(name)
    prods = products()
    cc = json.loads(json.dumps(var["components_config"]))
    filled = complete_image_urls(cc)
    if filled and not quiet:
        note(f"{filled} missing image URL field(s) filled from `original` for preview; "
             f"run `lab.py lint {name}` — the API and Android require all five")
    paywall_components = {
        "template_name": "components",
        "asset_base_url": "https://assets.pawwalls.com",
        "components_config": cc,
        "components_localizations": var["components_localizations"],
        "default_locale": var.get("default_locale", "en_US"),
        "revision": var.get("revision", 1),
        "automatically_scale_font_size": var.get("automatically_scale_font_size", True),
    }
    offerings = {
        "current_offering_id": "qa_lab",
        "offerings": [{"identifier": "qa_lab", "description": f"paywall-lab: {name}",
                       "packages": [], "paywall_components": paywall_components}],
        "ui_config": merged_ui_config(name),
    }
    shutil.rmtree(RES_DIR, ignore_errors=True)
    os.makedirs(os.path.join(RES_DIR, "qa"))
    save_json(os.path.join(RES_DIR, "qa", "offerings.json"), offerings)
    # iOS loader's package → product binding (SDK wire shape)
    save_json(os.path.join(RES_DIR, "packages.json"), {"packages": [
        {"identifier": p["identifier"],
         "platform_product_identifier": p.get("ios", {}).get("product_id") or p["identifier"].lstrip("$")}
        for p in prods["packages"]]})
    # Both harnesses' product mocks
    out = json.loads(json.dumps(prods))
    for p in out["packages"]:
        p["price"]["formatted"] = formatted_price(p["price"])
    save_json(os.path.join(RES_DIR, "products.json"), out)
    assets = os.path.join(variation_path(name), "assets")
    if os.path.isdir(assets):
        shutil.copytree(assets, os.path.join(RES_DIR, "qa", "pawwalls", "assets", "lab"))
        if not quiet:
            print(f"copied {len(os.listdir(assets))} local asset(s)")
    if not quiet:
        print(f"rendered {name} -> {os.path.relpath(RES_DIR, ROOT)}/")
    return RES_DIR


def cmd_render(args):
    render(args.name)


def cmd_preview(args):
    cfg = config()
    var_dir = variation_path(args.name)
    if args.generate:
        run_generate(var_dir)
    res = render(args.name)
    shots = os.path.join(var_dir, "screenshots")
    os.makedirs(shots, exist_ok=True)
    platforms = [args.platform] if args.platform != "all" else cfg.get("platforms", ["ios", "android"])
    produced = []
    for plat in platforms:
        fn = getattr(lab_platforms, f"preview_{plat}")
        produced += fn(cfg, ROOT, res, shots, build=args.build, states=args.states)
    print("\npreview complete:")
    for p in produced:
        print("  " + os.path.relpath(p, ROOT))
    print("review the screenshots, record approvals in NOTES.md, then lint → push.")


# ---------------------------------------------------------------- diff / lint
def _walk_diff(a, b, path, out):
    if type(a) is not type(b):
        out.append(f"{path}: type changed")
        return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: added")
            elif k not in b:
                out.append(f"{path}.{k}: removed")
            else:
                _walk_diff(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: list length {len(a)} -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _walk_diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: {json.dumps(a)[:60]} -> {json.dumps(b)[:60]}")


def cmd_diff(args):
    cfg = config()
    var = load_variation(args.name)
    _, _, data = fetch_paywall(cfg, args.paywall)
    comps = data["components"]
    base = working_copy(comps.get(args.against) or comps["published"])
    out = []
    _walk_diff(base["components_config"], var["components_config"], "config", out)
    print(f"--- live {args.against} vs variation {args.name}: components_config")
    print("\n".join(out) if out else "  (identical)")
    a = json.dumps(base["components_localizations"], indent=1, sort_keys=True)
    b = json.dumps(var["components_localizations"], indent=1, sort_keys=True)
    if a != b:
        print("--- localizations diff:")
        sys.stdout.writelines(difflib.unified_diff(a.splitlines(True), b.splitlines(True), "live", args.name, n=1))
    else:
        print("--- localizations: identical")


def cmd_lint(args):
    var = load_variation(args.name)
    findings = lab_lint.lint(var, merged_ui_config(args.name), products(),
                             assets_dir=os.path.join(variation_path(args.name), "assets"))
    errors = [f for f in findings if f.level == "error"]
    for f in findings:
        print(f"{f.level.upper():7} {f.rule}: {f.message}" + (f"  @ {f.path}" if f.path else ""))
    print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
    sys.exit(1 if errors else 0)


# ---------------------------------------------------------------- assets / push / create / publish
def cmd_upload_assets(args):
    cfg = config()
    assets = os.path.join(variation_path(args.name), "assets")
    if not os.path.isdir(assets):
        die("variation has no assets/ directory")
    ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mapping_path = os.path.join(variation_path(args.name), "uploaded_assets.json")
    mapping = load_json(mapping_path, default={})
    for f in sorted(os.listdir(assets)):
        ext = os.path.splitext(f)[1].lower()
        if ext not in ctype:
            continue
        if f in mapping:
            print(f"{f}: already uploaded, skipping")
            continue
        data = open(os.path.join(assets, f), "rb").read()
        resp = api("POST", "/media_assets", {
            "filename": f"lab-{args.name}-{f}", "content_type": ctype[ext],
            "file_data_base64": base64.b64encode(data).decode()}, cfg=cfg)
        mapping[f] = resp
        print(f"{f}: uploaded -> {resp.get('id')}")
    save_json(mapping_path, mapping)
    print(f"hosted-URL map saved to {os.path.relpath(mapping_path, ROOT)}")


def _hosted_image_urls(local_name, mapping):
    m = mapping.get(local_name)
    if not m:
        die(f"asset '{local_name}' not in uploaded_assets.json — run upload-assets first")
    base = (m.get("asset_base_url") or "").rstrip("/")
    formats = m.get("formats") or {}
    original = f"{base}/{m['object_name']}"

    def url(names):
        for n in names:
            if n in formats:
                return f"{base}/{formats[n]['object_name']}"
        return original
    return {"width": m.get("original_width"), "height": m.get("original_height"),
            "original": original, "heic": url(["heic"]), "heic_low_res": url(["heic_low_res", "heic"]),
            "webp": url(["webp"]), "webp_low_res": url(["webp_low_res", "webp"])}


def substitute_local_assets(var, name):
    """Replace local lab asset URLs with hosted media-library URLs. Refuses if unmapped."""
    if LOCAL_ASSET_BASE not in json.dumps(var["components_config"]):
        return var
    mapping_path = os.path.join(variation_path(name), "uploaded_assets.json")
    if not os.path.isfile(mapping_path):
        die(f"this variation references local lab assets ({LOCAL_ASSET_BASE}…) which don't exist on "
            f"RevenueCat's CDN.\nRun: python3 lab.py upload-assets {name}   then retry.")
    mapping = load_json(mapping_path)
    var = json.loads(json.dumps(var))

    def fix(n):
        orig = n.get("original")
        if isinstance(orig, str) and LOCAL_ASSET_BASE in orig:
            hosted = _hosted_image_urls(orig.split("/lab/")[-1], mapping)
            hosted["width"] = n.get("width") or hosted["width"]
            hosted["height"] = n.get("height") or hosted["height"]
            n.update(hosted)
    walk(var["components_config"], fix)
    if LOCAL_ASSET_BASE in json.dumps(var["components_config"]):
        die("some local asset URLs could not be substituted — check uploaded_assets.json")
    print("substituted local asset URLs with hosted media-library URLs")
    return var


def lint_gate(name, var):
    findings = lab_lint.lint(var, merged_ui_config(name), products(),
                             assets_dir=os.path.join(variation_path(name), "assets"))
    errors = [f for f in findings if f.level == "error"]
    if errors:
        for f in errors:
            print(f"ERROR   {f.rule}: {f.message}" + (f"  @ {f.path}" if f.path else ""))
        die(f"{len(errors)} lint error(s) — the API would reject this. Fix them (or --no-lint to try anyway).")


def cmd_push(args):
    if not args.yes:
        die("push uploads this variation as the RevenueCat DRAFT.\nIt is not user-visible, but it "
            "overwrites any existing draft.\nRe-run with --yes to proceed. (Close any dashboard builder "
            "tabs first — an open editor autosaves over API drafts.)")
    cfg = config()
    key, pw, data = fetch_paywall(cfg, args.paywall)
    comps = data["components"]
    current = comps.get("draft") or comps["published"]
    var = load_variation(args.name)
    if not args.no_lint:
        lint_gate(args.name, var)
    var = substitute_local_assets(var, args.name)
    body = {"revision": current["revision"], "components_config": var["components_config"],
            "components_localizations": var["components_localizations"]}
    result = api("PATCH", f"/paywalls/{pw['id']}", body, cfg=cfg)
    print(f"pushed '{args.name}' as draft of [{key}] — draft revision now {result['components']['draft']['revision']}")
    print("verify with: python3 lab.py status ; publish is a separate, human-approved step.")


def cmd_create(args):
    cfg = config()
    var = load_variation(args.name)
    if not args.no_lint:
        lint_gate(args.name, var)
    var = substitute_local_assets(var, args.name)
    body = {"name": args.title or args.name, "components_config": var["components_config"],
            "components_localizations": var["components_localizations"]}
    if args.offering:
        body["offering_id"] = args.offering
    result = api("POST", "/paywalls", body, cfg=cfg)
    slug = args.register or args.name
    cfg.setdefault("paywalls", {})[slug] = {"id": result["id"],
                                            "label": f"{body['name']} (created by lab.py from {args.name})",
                                            "offering_id": args.offering}
    save_json(CONFIG_PATH, cfg)
    print(f"created paywall '{body['name']}' -> {result['id']} (unpublished draft"
          f"{', offering ' + args.offering if args.offering else ', no offering'})")
    print(f"registered in config.json as [{slug}] — e.g. lab.py status / diff {args.name} --paywall {slug}")


def cmd_publish(args):
    if args.confirm != "PUBLISH":
        die("publishing makes the current RevenueCat draft LIVE for real users.\n"
            "Policy: requires explicit human approval in the current conversation, recorded in the\n"
            "variation's NOTES.md. Re-run with:  --confirm PUBLISH")
    cfg = config()
    key, pw, data = fetch_paywall(cfg, args.paywall)
    if data["components"].get("draft") is None:
        die("no draft to publish (draft == published)")
    result = api("POST", f"/paywalls/{pw['id']}/actions/publish", {}, cfg=cfg)
    print(f"published [{key}] — paywall revision now {result.get('revision')}")


# ---------------------------------------------------------------- suggest
SUGGEST_TEMPLATE = """## Intent
{intent}

## What I changed locally
{changes}

## Why it generalizes
{why}

## Evidence
{evidence}

<!-- Submitted with `lab.py suggest`. Upstream turns prompts into generalized changes; no PR needed. -->
"""


def cmd_suggest(args):
    import subprocess
    body = SUGGEST_TEMPLATE.format(
        intent=args.intent or "(what you wanted to achieve, in one or two sentences)",
        changes=args.changes or "(files/commands you touched; paste snippets or a `git diff --stat`)",
        why=args.why or "(why another RevenueCat team would hit the same thing)",
        evidence=args.evidence or "(screenshots, API error text, SDK version)")
    path = os.path.join(MY, "suggestions", datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(body)
    print(body)
    print(f"saved {os.path.relpath(path, ROOT)}")
    repo = args.repo or config_or_none() and config_or_none().get("upstream_repo") or "adamwatters/rc-paywall-lab-for-agents"
    if args.open:
        if not shutil.which("gh"):
            die("gh CLI not found — paste the text above into a new issue at https://github.com/" + repo + "/issues/new")
        title = args.title or (args.intent or "prompt")[:70]
        r = subprocess.run(["gh", "issue", "create", "-R", repo, "-t", f"[prompt] {title}", "-F", path, "-l", "prompt"],
                           capture_output=True, text=True)
        print(r.stdout or r.stderr)
    else:
        print(f"open it upstream with: python3 lab.py suggest --open ... (or paste into https://github.com/{repo}/issues/new)")


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("doctor"); sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("detect-sdk"); sp.add_argument("app_dir", nargs="?", default=".")
    sp.add_argument("--apply", action="store_true", help="pin both harnesses to the detected versions")
    sp = sub.add_parser("init"); sp.add_argument("--project", help="RevenueCat project id (proj...)")
    sub.add_parser("status")
    sp = sub.add_parser("pull"); sp.add_argument("--paywall")
    sp = sub.add_parser("new"); sp.add_argument("name")
    sp.add_argument("--source", default="published", help="published | draft | <variation> | <library design>")
    sp.add_argument("--paywall")
    sp = sub.add_parser("render"); sp.add_argument("name")
    sp = sub.add_parser("preview"); sp.add_argument("name")
    sp.add_argument("--platform", default="all", choices=["all", "ios", "android"])
    sp.add_argument("--build", action="store_true", help="force a harness rebuild")
    sp.add_argument("--generate", action="store_true", help="run the variation's generate.py first")
    sp.add_argument("--states", default="eligible,trial-used", help="comma list of eligibility states to capture")
    sp = sub.add_parser("diff"); sp.add_argument("name")
    sp.add_argument("--against", default="published", choices=["published", "draft"]); sp.add_argument("--paywall")
    sp = sub.add_parser("lint"); sp.add_argument("name")
    sp = sub.add_parser("upload-assets"); sp.add_argument("name")
    sp = sub.add_parser("push"); sp.add_argument("name"); sp.add_argument("--yes", action="store_true")
    sp.add_argument("--paywall"); sp.add_argument("--no-lint", action="store_true")
    sp = sub.add_parser("create"); sp.add_argument("name"); sp.add_argument("--title")
    sp.add_argument("--offering"); sp.add_argument("--register"); sp.add_argument("--no-lint", action="store_true")
    sp = sub.add_parser("publish"); sp.add_argument("--confirm", default=""); sp.add_argument("--paywall")
    sp = sub.add_parser("suggest")
    for a in ("intent", "changes", "why", "evidence", "title", "repo"):
        sp.add_argument("--" + a)
    sp.add_argument("--open", action="store_true", help="open as a GitHub issue upstream via gh")

    args = p.parse_args()
    for a in ("paywall",):
        if not hasattr(args, a):
            setattr(args, a, None)
    globals()[f"cmd_{args.cmd.replace('-', '_')}"](args)


if __name__ == "__main__":
    main()
