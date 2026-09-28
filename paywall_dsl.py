"""paywall_dsl — build RevenueCat Paywalls v2 (components) JSON from Python.

Raw paywall JSON is bound to one product set and one bag of localization ids.
Generating it from Python keeps a design reusable: the same generate.py renders
against anyone's `my/products.json`. Everything here emits exactly the shapes the
SDKs decode (purchases-ios 5.7x / purchases-android 10.x) and the API accepts.

    from paywall_dsl import *
    S = Strings()
    title = text(S.add("title", "Unlock everything"), fsize=28, weight="bold")
    write(paywall(stack([title, spacer(), ...], h="fill")), S)

Higher-level builders: eligibility_siblings, trial_toggle, badge_overlay,
footer_links, spacer, image with local assets, … (the why: docs/PAYWALL_JSON.md).
"""
import base64
import hashlib
import json
import os
import struct
import sys
import zlib

LOCAL_ASSET_BASE = "https://assets.pawwalls.com/lab"   # lab.py maps this to <variation>/assets/
WHITE = "#FFFFFFff"
BLACK = "#000000ff"

# ------------------------------------------------------------------ ids
_seq = {"n": 0}


def reset_ids():
    _seq["n"] = 0


def cid(prefix="c"):
    """Deterministic component id (stable across regenerations → clean diffs)."""
    _seq["n"] += 1
    return f"{prefix}_{_seq['n']:03d}"


def lid(name):
    """Localization id derived from a readable name. RevenueCat's API only accepts
    ids that are exactly 10 chars of [A-Za-z0-9_-] (HTTP 422 otherwise)."""
    return base64.urlsafe_b64encode(hashlib.sha1(name.encode()).digest())[:10].decode()


# ------------------------------------------------------------------ primitives
def hexcol(light, dark=None):
    c = {"light": {"type": "hex", "value": light}}
    if dark:
        c["dark"] = {"type": "hex", "value": dark}
    return c


def gradient(degrees, stops):
    """Linear gradient color value. stops = [(hex, percent), …]."""
    return {"light": {"type": "linear", "degrees": degrees,
                      "points": [{"color": c, "percent": p} for c, p in stops]}}


def edges(top=0, leading=0, bottom=0, trailing=0):
    return {"top": top, "leading": leading, "bottom": bottom, "trailing": trailing}


def size(w="fill", h="fit"):
    def part(v):
        if isinstance(v, (int, float)):
            return {"type": "fixed", "value": v}
        return {"type": v, "value": None}
    return {"width": part(w), "height": part(h)}


def rounded(radius):
    return {"type": "rectangle", "corners": {"top_leading": radius, "top_trailing": radius,
                                             "bottom_leading": radius, "bottom_trailing": radius}}


PILL = {"type": "pill", "corners": None}


def image_urls(file, w, h, base=LOCAL_ASSET_BASE):
    """All FIVE url fields: the API requires them and Android's decoder refuses
    sources without webp/webp_low_res. Pointing every field at one PNG is fine —
    both platforms sniff the real format. `lab.py push` swaps in hosted URLs."""
    url = f"{base}/{file}"
    return {"light": {"width": w, "height": h, "original": url, "heic": url, "heic_low_res": url,
                      "webp": url, "webp_low_res": url}}


def text(lid_, color=BLACK, fsize=16, weight="regular", align="center", w="fill",
         margin=None, padding=None, font=None, overrides=None, visible=None, name=""):
    weight_int = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700,
                  "heavy": 800, "black": 900, "light": 300}[weight]
    node = {"type": "text", "id": cid("txt"), "name": name, "text_lid": lid_,
            "color": hexcol(color) if isinstance(color, str) else color, "background_color": None,
            "font_name": font, "font_size": fsize, "font_weight": weight, "font_weight_int": weight_int,
            "horizontal_alignment": align, "size": size(w, "fit"),
            "padding": padding or edges(), "margin": margin or edges()}
    if overrides:
        node["overrides"] = overrides
    if visible is not None:
        node["visible"] = visible
    return node


def stack(components, axis="vertical", alignment="center", distribution="start", spacing=0,
          w="fill", h="fit", padding=None, margin=None, background=None, shape=None, border=None,
          shadow=None, badge=None, name="", overrides=None, visible=None):
    """Flex-like container. axis: vertical | horizontal | zlayer."""
    node = {"type": "stack", "id": cid("stk"), "name": name, "components": components,
            "dimension": {"type": axis, "alignment": alignment, "distribution": distribution},
            "spacing": spacing, "size": size(w, h), "padding": padding or edges(), "margin": margin or edges(),
            "background": background, "background_color": None, "shape": shape, "border": border,
            "shadow": shadow, "badge": badge}
    if overrides:
        node["overrides"] = overrides
    if visible is not None:
        node["visible"] = visible
    return node


def color_background(hex_or_value):
    return {"type": "color", "value": hexcol(hex_or_value) if isinstance(hex_or_value, str) else hex_or_value}


def image_background(file, w, h, fit="fill"):
    return {"type": "image", "value": image_urls(file, w, h), "fit_mode": fit, "color_overlay": None}


def image(file, w, h, display_w=None, display_h=None, fit="fit", mask=None, name="", margin=None):
    """Image component from a local asset (drop the file in <variation>/assets/).
    w/h = pixel size of the file; display_w/h = points on screen (default: fit width)."""
    return {"type": "image", "id": cid("img"), "name": name, "source": image_urls(file, w, h),
            "size": size(display_w if display_w is not None else "fill", display_h if display_h is not None else "fit"),
            "fit_mode": fit, "mask_shape": mask, "padding": edges(), "margin": margin or edges(),
            "border": None, "shadow": None, "color_overlay": None}


def spacer():
    """Fill-height empty stack. Use explicit spacers rather than distribution=space_evenly:
    the SDK inserts a flex gap per child *including hidden ones*, so eligibility states
    would space differently."""
    return stack([], w="fill", h="fill", name="Spacer")


def package(package_id, content, selected=False):
    return {"type": "package", "id": cid("pkg"), "name": "", "package_id": package_id,
            "is_selected_by_default": selected, "stack": content}


def purchase_button(content):
    return {"type": "purchase_button", "id": cid("cta"), "name": "", "stack": content}


def button(action, content):
    return {"type": "button", "id": cid("btn"), "name": "", "action": action, "stack": content}


def restore_action():
    return {"type": "restore_purchases"}


def navigate_action(url_lid, destination="url"):
    """destination: terms | privacy_policy | url — the url itself is a localized string."""
    return {"type": "navigate_to", "destination": destination, "sheet": None,
            "url": {"method": "external_browser", "url_lid": url_lid}}


def tab(name, components):
    return {"type": "tab", "id": cid("tab"), "name": name, "stack": stack(components, name=name)}


def tab_control():
    """Placeholder that renders the tabs' control (the switch) inside a tab's content."""
    return {"type": "tab_control", "id": cid("tabctl"), "name": ""}


# ------------------------------------------------------------------ rules (overrides)
INTRO = {"type": "intro_offer_condition", "operator": "=", "value": True}
SELECTED = {"type": "selected"}


def when(condition, **props):
    return {"conditions": [condition], "properties": props}


def show_when_intro():
    return [when(INTRO, visible=True)]


def hide_when_intro():
    return [when(INTRO, visible=False)]


def when_selected(**props):
    """e.g. when_selected(background=color_background(...), border={...})"""
    return when(SELECTED, **props)


def eligibility_siblings(trial_node, no_trial_node):
    """The builder-legible eligibility pattern (docs/PAYWALL_JSON.md):
    two TOP-LEVEL siblings — `trial_node` base-hidden and shown when an intro offer is
    available, `no_trial_node` base-visible and hidden when it is. Base state = the
    trial-INELIGIBLE layout, which is also the safe fallback for old SDKs."""
    trial_node["visible"] = False
    trial_node["overrides"] = (trial_node.get("overrides") or []) + show_when_intro()
    no_trial_node["overrides"] = (no_trial_node.get("overrides") or []) + hide_when_intro()
    return trial_node, no_trial_node


def badge_overlay(label_lid, background, color=WHITE, fsize=13, alignment="top_trailing", inset=16):
    """Pill badge floating over a card's edge (set as stack(badge=...)).
    `background` may be a hex string, a gradient() value, or a full background object."""
    if isinstance(background, str) or "type" not in background:
        background = color_background(background)
    return {"style": "overlay", "alignment": alignment,
            "stack": stack([text(label_lid, color=color, fsize=fsize, weight="bold", w="fit")],
                           w="fit", margin=edges(trailing=inset),
                           padding=edges(top=7, leading=16, bottom=7, trailing=16),
                           background=background, shape=PILL)}


def trial_toggle(tab_off_components, tab_on_components, track_on, track_off="#E5E5EAff",
                 thumb="#FFFFFFff", name="Switch", default_on=False):
    """The 'Not sure yet? Start free trial' switch as a tabs component. Put a
    tab_control() inside each tab's toggle row so the switch renders in place."""
    off, on = tab("Tab OFF", tab_off_components), tab("Tab ON", tab_on_components)
    return {"type": "tabs", "id": cid("tabs"), "name": name,
            "control": {"type": "toggle", "stack": stack(
                [{"type": "tab_control_toggle", "id": cid("toggle"), "name": "", "default_value": default_on,
                  "thumb_color_off": {"light": {"type": "hex", "value": thumb}},
                  "thumb_color_on": {"light": {"type": "hex", "value": thumb}},
                  "track_color_off": {"light": {"type": "hex", "value": track_off}},
                  "track_color_on": {"light": {"type": "hex", "value": track_on}}}],
                alignment="leading", w="fit")},
            "default_tab_id": (on if default_on else off)["id"], "tabs": [off, on],
            "size": size("fill", "fit"), "padding": edges(), "margin": edges(), "background": None, "shape": None}


def footer_links(strings, color="#555555ff", fsize=13, terms_url=None, privacy_url=None, margin=None):
    """Restore / Terms / Privacy row — App Store review expects these."""
    def link(label_lid, action):
        return button(action, stack([text(label_lid, color=color, fsize=fsize, weight="semibold", w="fit")],
                                    w="fit", padding=edges(top=8, leading=10, bottom=8, trailing=10)))
    items = [link(strings.add("footer_restore", "Restore Purchases"), restore_action())]
    if terms_url:
        items.append(link(strings.add("footer_terms", "Terms"),
                          navigate_action(strings.add("footer_terms_url", terms_url), "terms")))
    if privacy_url:
        items.append(link(strings.add("footer_privacy", "Privacy"),
                          navigate_action(strings.add("footer_privacy_url", privacy_url), "privacy_policy")))
    return stack(items, axis="horizontal", alignment="top", distribution="center", spacing=8,
                 name="Footer links", margin=margin or edges(top=12))


# ------------------------------------------------------------------ strings / products / output
class Strings:
    """Copy bag. add(key, text) mints a stable 10-char lid from the key."""

    def __init__(self, locale="en_US"):
        self.locale = locale
        self.map = {}

    def add(self, key, value):
        l = lid(key)
        self.map[l] = value
        return l

    def localizations(self):
        return {self.locale: dict(self.map)}


def lab_home():
    return os.path.abspath(os.environ.get("PAYWALL_LAB_HOME") or os.path.join(
        os.environ.get("PAYWALL_LAB_ROOT", os.path.dirname(os.path.abspath(__file__))), "my"))


def products():
    """Packages from my/products.json (or the example file) — generators iterate these."""
    for p in (os.path.join(lab_home(), "products.json"), os.path.join(lab_home(), "products.example.json")):
        if os.path.isfile(p):
            return json.load(open(p))["packages"]
    raise SystemExit("no products.json — run `python3 lab.py init` or copy my/products.example.json")


def trial_days(pkg):
    t = pkg.get("trial")
    if not t:
        return 0
    return t["count"] * {"day": 1, "week": 7, "month": 30, "year": 365}[t["unit"]]


# Variables the SDK resolves per package at render time (SDK ≥ 5.6 / 8.x):
V_PRICE = "{{ product.price }}"
V_PRICE_PER_MONTH = "{{ product.price_per_month }}"
V_PRICE_PER_PERIOD = "{{ product.price_per_period }}"
V_PERIOD = "{{ product.period }}"           # "month", "year"
V_PERIODLY = "{{ product.periodly }}"       # "monthly", "yearly"
V_PERIOD_MONTHS = "{{ product.period_in_months }}"
V_OFFER_PERIOD = "{{ product.offer_period }}"   # e.g. "7 days"
V_NAME = "{{ product.store_product_name }}"


def paywall(root_stack, strings, background=None, header=None, sticky_footer=None, scale_font=True):
    return {"components_config": {"base": {"background": background or color_background(WHITE),
                                           "header": header, "stack": root_stack, "sticky_footer": sticky_footer}},
            "components_localizations": strings.localizations(),
            "default_locale": strings.locale, "revision": 1, "automatically_scale_font_size": scale_font}


def write(out, path=None):
    caller_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    path = path or os.path.join(caller_dir, "paywall.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {path}")


# ------------------------------------------------------------------ placeholder assets (stdlib PNG)
def write_png(path, w, h, pixel):
    """Write an RGBA PNG with pixel(x, y) -> (r, g, b, a). Stdlib only — for
    generated placeholder art (gradients, blobs) without shipping binaries."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw.extend(pixel(x, y))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


def mesh_gradient(path, w, h, anchors):
    """Inverse-distance blend of colored anchors — a mesh-gradient stand-in.
    anchors = [((x_frac, y_frac), (r, g, b)), …]"""
    def px(x, y):
        fx, fy = x / w, y / h
        num = [0.0, 0.0, 0.0]
        den = 0.0
        for (ax, ay), col in anchors:
            d2 = (fx - ax) ** 2 + (fy - ay) ** 2 + 0.02
            wgt = 1.0 / d2
            den += wgt
            for i in range(3):
                num[i] += col[i] * wgt
        return (int(num[0] / den), int(num[1] / den), int(num[2] / den), 255)
    write_png(path, w, h, px)
