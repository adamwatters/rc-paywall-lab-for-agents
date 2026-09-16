"""Lint rules for RevenueCat Paywalls v2 JSON — every rule here is something the
API, an SDK, or the dashboard builder actually rejected or mis-rendered on us.
Errors = the API/SDK will reject or break. Warnings = works but will bite you.

Add a rule when you learn one (and `lab.py suggest` it upstream)."""
import os
import re
from dataclasses import dataclass

LOCAL_ASSET_BASE = "https://assets.pawwalls.com/lab/"
LID_RE = re.compile(r"^[A-Za-z0-9_-]{10}$")
IMAGE_URL_FIELDS = ("original", "heic", "heic_low_res", "webp", "webp_low_res")
KNOWN_COMPONENTS = {"stack", "text", "image", "icon", "package", "purchase_button", "button", "tabs", "tab",
                    "tab_control", "tab_control_toggle", "tab_control_button", "carousel", "timeline",
                    "timeline_item", "video", "footer"}
KNOWN_CONDITIONS = {"intro_offer", "promo_offer", "selected", "compact", "medium", "expanded",
                    "intro_offer_condition", "promo_offer_condition", "selected_condition"}
TRIAL_WORDS = re.compile(r"\b(free trial|days? free|trial)\b", re.I)


@dataclass
class Finding:
    level: str
    rule: str
    message: str
    path: str = ""


def _components(node, path="config", inside_tabs=False):
    """Yield (component_dict, path, inside_tabs) for every component in the tree."""
    if isinstance(node, dict):
        is_comp = "id" in node and isinstance(node.get("type"), str)
        if is_comp:
            yield node, path, inside_tabs
        for k, v in node.items():
            child_in_tabs = inside_tabs or (is_comp and node.get("type") == "tabs" and k == "tabs")
            yield from _components(v, f"{path}.{k}", child_in_tabs)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _components(v, f"{path}[{i}]", inside_tabs)


def _image_sources(node, path="config"):
    if isinstance(node, dict):
        if "original" in node and isinstance(node.get("original"), str):
            yield node, path
        for k, v in node.items():
            yield from _image_sources(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _image_sources(v, f"{path}[{i}]")


def lint(var, ui_config, products, assets_dir=None):
    out = []
    cc = var.get("components_config", {})
    base = cc.get("base", {})
    locale = var.get("default_locale", "en_US")
    locs = var.get("components_localizations", {})
    strings = locs.get(locale, {})
    if locale not in locs:
        out.append(Finding("error", "default-locale", f"default_locale '{locale}' has no entry in components_localizations"))

    # --- localization ids: the API rejects free-form ids (learned via HTTP 422)
    for lid in strings:
        if not LID_RE.match(lid):
            out.append(Finding("error", "lid-format",
                               f"localization id '{lid}' must be exactly 10 chars of [A-Za-z0-9_-] "
                               f"(use paywall_dsl.lid('readable name'))"))
    referenced = set()
    for comp, path, _ in _components(cc):
        holders = [comp] + [o.get("properties", {}) for o in comp.get("overrides", []) or []]
        url = ((comp.get("action") or {}).get("url") or {})
        for lid, kind in [(h.get("text_lid"), "text_lid") for h in holders] + [(url.get("url_lid"), "url_lid")]:
            if lid:
                referenced.add(lid)
                if lid not in strings:
                    out.append(Finding("error", "lid-missing", f"{kind} '{lid}' not in {locale} localizations", path))
    unused = sorted(set(strings) - referenced)
    if unused:
        out.append(Finding("warning", "lid-unused", f"{len(unused)} unreferenced localization id(s): {', '.join(unused[:6])}"
                           + (" …" if len(unused) > 6 else "")))

    # --- image sources: API requires all five URL fields; Android's decoder requires webp ones
    for src, path in _image_sources(cc):
        missing = [k for k in IMAGE_URL_FIELDS if not src.get(k)]
        if missing:
            out.append(Finding("error", "image-urls", f"image source missing {', '.join(missing)} "
                               f"(Android and the API require all of {', '.join(IMAGE_URL_FIELDS)})", path))
        if not isinstance(src.get("width"), int) or not isinstance(src.get("height"), int):
            out.append(Finding("error", "image-size", "image source needs integer width and height", path))
        if LOCAL_ASSET_BASE in src.get("original", ""):
            fname = src["original"].split("/lab/")[-1]
            if not assets_dir or not os.path.isfile(os.path.join(assets_dir, fname)):
                out.append(Finding("error", "local-asset-missing", f"references local asset '{fname}' "
                                   f"but variations/<name>/assets/{fname} does not exist", path))

    # --- footer: the API's type name is "footer" (not "sticky_footer") — learned via 422
    sf = base.get("sticky_footer")
    if sf is not None and sf.get("type") != "footer":
        out.append(Finding("error", "footer-type", f"base.sticky_footer.type must be \"footer\" (got {sf.get('type')!r})",
                           "config.base.sticky_footer"))

    # --- component & condition vocab
    known_pkgs = {p["identifier"] for p in products.get("packages", [])}
    saw_intro_rule = False
    for comp, path, in_tabs in _components(cc):
        t = comp.get("type")
        if t not in KNOWN_COMPONENTS:
            out.append(Finding("warning", "unknown-component", f"component type '{t}' is not in the known set "
                               f"(fine if your SDK version supports it; old SDKs skip unknown components)", path))
        if t == "package" and comp.get("package_id") not in known_pkgs:
            out.append(Finding("warning", "package-unknown", f"package_id '{comp.get('package_id')}' is not in "
                               f"my/products.json — it will render empty locally (and in prod if the offering lacks it)", path))
        for o in comp.get("overrides", []) or []:
            for c in o.get("conditions", []) or []:
                ct = c.get("type")
                if ct in ("intro_offer", "intro_offer_condition"):
                    saw_intro_rule = True
                if ct not in KNOWN_CONDITIONS:
                    out.append(Finding("warning", "unknown-condition", f"override condition '{ct}' unknown — old SDKs "
                                       f"drop the whole override (author the base state as the safe fallback)", path))
            if in_tabs and "visible" in (o.get("properties") or {}):
                out.append(Finding("warning", "nested-visibility-rule",
                                   "show/hide rule on a component nested inside a tabs state: the SDK honors it, "
                                   "but the dashboard builder's rules UI cannot list, preview, or edit it. "
                                   "See library/recipes/eligibility-siblings.md for the builder-legible construction", path))
        fn = comp.get("font_name")
        if fn:
            entry = (ui_config.get("app", {}).get("fonts") or {}).get(fn)
            if not entry:
                out.append(Finding("warning", "font-alias", f"font_name '{fn}' has no alias in ui_config — falls back to "
                                   f"the system font in production until registered with RevenueCat", path))
            else:
                for plat in ("ios", "android"):
                    if plat not in entry:
                        out.append(Finding("warning", "font-alias", f"font alias '{fn}' has no '{plat}' face", path))

    # --- trial copy shown to trial-ineligible users
    if not saw_intro_rule and any(TRIAL_WORDS.search(s) for s in strings.values() if isinstance(s, str)):
        out.append(Finding("warning", "trial-copy-unconditional",
                           "copy mentions a trial but no intro-offer rule exists: users who already used their "
                           "trial (or store accounts that aren't eligible) will be promised a trial they won't get. "
                           "See library/recipes/eligibility-siblings.md"))
    return out
