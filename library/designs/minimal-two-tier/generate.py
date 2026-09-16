#!/usr/bin/env python3
"""minimal-two-tier — the clean starting point. No images.

Headline, three benefit rows, a card per package, CTA, footer links. Eligibility
is handled two ways so you can see both patterns: the headline uses the builder-
legible siblings recipe; the CTA label uses a text override (trial-eligible users
see "Start free trial", everyone else "Continue"). Base state = trial-ineligible.

Run: python3 generate.py   → paywall.json   then: lab.py preview <name>
"""
import os
import sys

sys.path.insert(0, os.environ.get("PAYWALL_LAB_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
from paywall_dsl import *  # noqa: E402,F403

# ---------------------------------------------------------------- palette
BG = "#FFFFFFff"
INK = "#111111ff"
INK_SOFT = "#6B6B6Bff"
ACCENT = "#2F6BFFff"
CARD_BORDER = "#E3E3E3ff"
CARD_SELECTED_BG = "#EEF3FFff"

reset_ids()
S = Strings()
pkgs = products()
selected = pkgs[0]
days = trial_days(selected)

# ---------------------------------------------------------------- copy
h_trial = S.add("h_trial", f"Try everything free for {days} days")
h_notrial = S.add("h_notrial", "Unlock everything")
benefits = [S.add(f"benefit_{i}", b) for i, b in enumerate([
    "Unlimited access to every feature", "Sync across all your devices", "Cancel anytime"])]
check = S.add("check", "✓")
cta = S.add("cta", "Continue")
cta_trial = S.add("cta_trial", "Start free trial")
fine_print = S.add("fine_print", f"{V_PRICE} per {V_PERIOD}. Cancel anytime.")
card_title = {p["identifier"]: S.add(f"card_title_{p['identifier']}", p["name"]) for p in pkgs}
card_price = S.add("card_price", f"{V_PRICE} / {V_PERIOD}")
card_per_month = S.add("card_per_month", f"{V_PRICE_PER_MONTH} per month")

# ---------------------------------------------------------------- pieces
headline_a = stack([text(h_trial, color=INK, fsize=30, weight="bold")], name="Headline (trial)")
headline_b = stack([text(h_notrial, color=INK, fsize=30, weight="bold")], name="Headline (no trial)")
eligibility_siblings(headline_a, headline_b)

benefit_rows = stack([
    stack([text(check, color=ACCENT, fsize=16, weight="bold", w="fit", margin=edges(trailing=10)),
           text(b, color=INK, fsize=16, align="leading")], axis="horizontal", alignment="center")
    for b in benefits], spacing=12, name="Benefits", margin=edges(top=24))


def card(p):
    body = stack([
        stack([text(card_title[p["identifier"]], color=INK, fsize=17, weight="semibold", align="leading", w="fit"),
               text(card_per_month, color=INK_SOFT, fsize=13, align="leading", w="fit")],
              alignment="leading", w="fit", spacing=2),
        text(card_price, color=INK, fsize=15, weight="medium", align="trailing", w="fit"),
    ], axis="horizontal", distribution="space_between", padding=edges(top=14, leading=18, bottom=14, trailing=18),
        background=color_background(BG), shape=rounded(14), border={"color": hexcol(CARD_BORDER), "width": 1.5},
        overrides=[when_selected(background=color_background(CARD_SELECTED_BG),
                                 border={"color": hexcol(ACCENT), "width": 2})])
    return package(p["identifier"], body, selected=(p is selected))


cards = stack([card(p) for p in pkgs], spacing=10, name="Packages")

cta_button = purchase_button(stack(
    [text(cta, color=WHITE, fsize=18, weight="semibold", w="fit",
          overrides=[when({"type": "intro_offer"}, text_lid=cta_trial)] if days else None)],
    padding=edges(top=16, leading=24, bottom=16, trailing=24), margin=edges(top=14),
    background=color_background(ACCENT), shape=rounded(14)))

content = stack([
    spacer(), headline_a, headline_b, benefit_rows, spacer(), cards, cta_button,
    text(fine_print, color=INK_SOFT, fsize=12, margin=edges(top=10)),
    footer_links(S, color="#9A9A9Aff", terms_url="https://example.com/terms", privacy_url="https://example.com/privacy"),
], name="Content", h="fill", margin=edges(top=60, leading=20, trailing=20, bottom=24))

write(paywall(content, S, background=color_background(BG)))
