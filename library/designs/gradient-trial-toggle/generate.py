#!/usr/bin/env python3
"""gradient-trial-toggle — trial-forward paywall on a mesh gradient.

Headline + subhead, a social-proof strip (photo tiles + quote), then the offer
block: a "Not sure yet? Start free trial" switch (tabs component) over the plan
cards and CTA. Eligibility handled builder-legibly: base state is the trial-
INELIGIBLE layout; two top-level headline stacks and the switch/plain-offers pair
flip on the intro-offer rule. Single full-height column with explicit spacers
(no sticky footer) so it renders identically in the SDK, the dashboard preview,
and on small phones.

Parameterized by my/products.json: one card per package (first = selected), copy
uses product variables, trial length comes from the selected package. Placeholder
assets are generated (stdlib) if missing — replace assets/*.png with your own.

Run: python3 generate.py   → paywall.json (+ assets/)   then: lab.py preview <name>
"""
import os
import sys

sys.path.insert(0, os.environ.get("PAYWALL_LAB_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
from paywall_dsl import *  # noqa: E402,F403

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- palette (swap for your brand)
CTA = "#E9396Fff"
CARD_SELECTED_BG = "#FBECF0ff"
CARD_SELECTED_BORDER = "#EA5C8Aff"
CARD_BG = "#FFFFFFff"
INK = "#3A1A2Aff"           # card titles / prices
INK_SOFT = "#7B5A69ff"      # card secondary line
QUOTE = "#7C4B60ff"
NAME = "#310116ff"
BADGE = gradient(90, [("#FE6D5Bff", 0), ("#FE4F63ff", 100)])
LINK = "#5A3A4899"

# ---------------------------------------------------------------- placeholder assets
def ensure_assets():
    bg = os.path.join(HERE, "assets", "bg.png")
    if not os.path.isfile(bg):
        mesh_gradient(bg, 201, 437, [((0.05, 0.10), (232, 92, 160)), ((0.95, 0.15), (250, 170, 110)),
                                     ((0.10, 0.60), (245, 160, 170)), ((0.90, 0.75), (250, 200, 140)),
                                     ((0.50, 1.00), (252, 235, 190))])
    strip = os.path.join(HERE, "assets", "photo_strip.png")
    if not os.path.isfile(strip):
        tiles = [((10, 8, 70, 80), (120, 170, 220)), ((70, 4, 130, 84), (230, 160, 120)), ((132, 12, 200, 88), (160, 200, 150))]

        def px(x, y):
            for (x0, y0, x1, y1), col in reversed(tiles):
                if x0 <= x < x1 and y0 <= y < y1:
                    edge = x - x0 < 3 or x1 - x <= 3 or y - y0 < 3 or y1 - y <= 3
                    return (255, 255, 255, 255) if edge else (*col, 255)
            return (0, 0, 0, 0)
        write_png(strip, 208, 96, px)


ensure_assets()
reset_ids()
S = Strings()
pkgs = products()
selected = pkgs[0]
days = trial_days(selected)
HAS_TRIAL = days > 0

# ---------------------------------------------------------------- copy (placeholders — edit freely)
h1a, h1b, h1c = S.add("h_trial_1", "Start your"), S.add("h_trial_2", f"{days} day free"), S.add("h_trial_3", "trial to unlock everything")
h2a, h2b = S.add("h_notrial_1", "Unlock"), S.add("h_notrial_2", "everything you need")
subhead_lid = S.add("subhead", "Join 50,000+ people already inside")
quote_lid = S.add("quote", "“Two weeks in and it already feels like part of my routine.”")
quote_by = S.add("quote_by", "Sam R.")
toggle_lid = S.add("toggle", "Not sure yet? Start free trial")
badge_lid = S.add("badge_trial", f"{days} DAYS FREE")
cta_lid, cta_trial_lid = S.add("cta", "Continue"), S.add("cta_trial", "Continue for free")
card_title = {p["identifier"]: S.add(f"card_title_{p['identifier']}", p["name"]) for p in pkgs}
card_sub = S.add("card_sub", f"{V_PERIOD_MONTHS} mo • {V_PRICE}")
card_price = S.add("card_price", f"{V_PRICE_PER_MONTH}/month")


# ---------------------------------------------------------------- pieces
def headline_span(l, bold):
    return text(l, color=WHITE, fsize=30, weight="bold" if bold else "regular", w="fit")


def headline_line(spans):
    return stack(spans, axis="horizontal", w="fit", spacing=7)


def subhead():
    return text(subhead_lid, color=WHITE, fsize=18, margin=edges(top=12, leading=16, trailing=16))


headline_trial = stack([headline_line([headline_span(h1a, False), headline_span(h1b, True)]),
                        headline_line([headline_span(h1c, False)]), subhead()],
                       spacing=2, name="Headline (trial)")
headline_notrial = stack([headline_line([headline_span(h2a, False)]), headline_line([headline_span(h2b, True)]),
                          subhead()], spacing=2, name="Headline (no trial)")

social_proof = stack([
    image("photo_strip.png", 208, 96, display_w=104, display_h=48, name="photo strip"),
    text(quote_lid, color=QUOTE, fsize=16, margin=edges(top=24, leading=12, trailing=12)),
    text(quote_by, color=NAME, fsize=17, weight="bold", margin=edges(top=10)),
], name="Social proof")


def plan_card(p, with_badge):
    labels = stack([text(card_title[p["identifier"]], color=INK, fsize=18, weight="bold", align="leading", w="fit"),
                    text(card_sub, color=INK_SOFT, fsize=14, weight="medium", align="leading", w="fit")],
                   alignment="leading", w="fit", spacing=3)
    price = text(card_price, color=INK, fsize=17, weight="semibold", align="trailing", w="fit")
    card = stack([labels, price], axis="horizontal", distribution="space_between",
                 padding=edges(top=13, leading=22, bottom=13, trailing=22),
                 background=color_background(CARD_BG), shape=rounded(18),
                 border={"color": hexcol(CARD_BG), "width": 2},
                 badge=badge_overlay(badge_lid, BADGE) if with_badge else None,
                 overrides=[when_selected(background=color_background(CARD_SELECTED_BG),
                                          border={"color": hexcol(CARD_SELECTED_BORDER), "width": 2})])
    return package(p["identifier"], card, selected=(p is selected))


def offers(with_badges, cta, top=14):
    cards = stack([plan_card(p, with_badges) for p in pkgs], spacing=10, name="Package stack", padding=edges(top=top))
    button_ = purchase_button(stack([text(cta, color=WHITE, fsize=19, weight="semibold", w="fit")],
                                    padding=edges(top=16, leading=32, bottom=16, trailing=32), margin=edges(top=12),
                                    background=color_background(CTA), shape=rounded(16)))
    return [cards, button_]


def toggle_row():
    return stack([text(toggle_lid, color=INK, fsize=16, align="leading", w="fit"), tab_control()],
                 axis="horizontal", distribution="space_between", name="Switch and text",
                 padding=edges(top=10, leading=24, bottom=10, trailing=12),
                 background=color_background(WHITE), shape=PILL)


offer_block = []
if HAS_TRIAL:
    switch = trial_toggle([toggle_row()] + offers(False, cta_lid, top=10),
                          [toggle_row()] + offers(True, cta_trial_lid, top=10), track_on=CTA)
    plain = stack(offers(False, cta_lid), name="Offers (no trial)")
    eligibility_siblings(headline_trial, headline_notrial)
    eligibility_siblings(switch, plain)
    offer_block = [switch, plain]
    headlines = [headline_trial, headline_notrial]
else:
    offer_block = [stack(offers(False, cta_lid), name="Offers")]
    headlines = [headline_notrial]

content = stack([spacer(), *headlines, spacer(), social_proof, spacer(), *offer_block,
                 footer_links(S, color=LINK, terms_url="https://example.com/terms",
                              privacy_url="https://example.com/privacy")],
                name="Content", h="fill", margin=edges(top=44, leading=16, trailing=16, bottom=30))

write(paywall(content, S, background=image_background("bg.png", 201, 437)))
