# RevenueCat dashboard builder gaps (why this lab exists)

> Verbatim findings report, lightly anonymized. TL;DR: (1) the rule editor can't target anything inside a `tabs` component; (2) the rules list and preview only reverse-parse a subset of the overrides the SDK honors, so API-written rules can be live yet invisible. Consequence: the lab's dual-state simulator screenshots are the review surface, and the `eligibility-siblings` recipe is the builder-legible construction.

---

# Paywall builder: eligibility rules can't reach inside toggle (tabs) designs, and the rules UI doesn't surface all SDK-honored overrides

Findings from controlled experiments, August 2026 (reported to RevenueCat). Reproduce with any components paywall containing a `tabs` component.

## Summary

Two related problems, found while trying to make a trial-toggle paywall
honest for trial-ineligible users:

1. **Authoring gap:** the Paywall logic rule editor cannot target any
   component nested inside a `tabs` component's tab stacks — precisely where
   toggle-template paywalls keep the trial copy that eligibility rules exist
   to control. The intended fix ("hide the trial-toggle row when no intro
   offer is available") cannot be expressed in the builder at all.
2. **Display gap:** after writing the correct override via the public API v2
   (which accepts `components_config` writes), the builder's rule list and
   its Default/Introductory rules preview only reverse-parse a **subset** of
   the overrides RevenueCatUI evaluates at runtime. The override is absent
   from the rule list and ignored by the preview in either condition
   encoding, while the SDK (verified on purchases-ios **5.76.0**) renders it
   correctly. The builder thus shows "no rules" on a paywall with live
   conditional behavior.

A secondary asymmetry: the builder currently *writes* new visibility rules in
the extended condition encoding (`{"type": "intro_offer_condition",
"operator": "=", "value": true}`) but *lists* legacy-form
(`{"type": "intro_offer"}`) **text** overrides — and converting those text
overrides to the extended encoding makes them vanish from the rule list too.

## Part 1 — the authoring dead-end (what started this)

**Context.** The paywall under test uses the standard trial-toggle pattern: the
entire offer area is one `tabs` component with a toggle control and OFF/ON
tab states, each state containing its own "Switch and text" row (the
"Not sure yet? Start free trial" label + toggle), package stack, and purchase
button. The needed change: for intro-ineligible users — whom Apple charges
immediately despite the trial promise — hide the trial-toggle row while
keeping packages and the purchase button.

The rule system has the right primitives (Offer type rules with Show layer /
Hide layer / Modify layer), but they can't be aimed at the target:

- **The rule editor's layer picker stops at the tabs boundary.** Its tree
  lists all top-level layers, but the tabs component appears as a leaf: none
  of its children (tab states, toggle row, package stacks, CTA) are
  enumerable. The picker's alternate path — "click here to select a layer
  from the preview" — never registered a selection for components inside the
  tabs in repeated attempts, while list-picking top-level layers worked
  instantly.
- **The only expressible rule is the wrong one.** "Hide layer → tabs
  component" is the sole hide the editor can author on this design — and it
  removes the packages and purchase button along with the trial copy,
  leaving nothing to buy.
- **No other editor surface fills the gap.** The Layers panel offers no
  visibility control for the nested row (its properties are layout/fill
  only; its context menu is rename/duplicate/copy-styles/delete), so
  "hidden in base + shown via rule" cannot be set up for nested layers.
- **Telling asymmetry:** text components *do* have a per-eligibility
  affordance (the intro-offer string variant in the text panel) — which is
  how the CTA-label rule on the same paywall was authored *inside* the tabs.
  Eligibility-conditional **content** works at any depth; eligibility-
  conditional **visibility** — what a toggle design actually needs — only
  exists in the rules panel, whose picker can't reach inside toggles.

Net: the trial-toggle template and the intro-eligibility rules feature don't
compose. This forced us to write the override through the public API, which
surfaced Part 2.

## Part 2 — the rules UI reverse-parsing gaps

## Environment / method

- Paywall: components paywall "Quarterly + Annual" (`pw9203a483b4e148f6`),
  which contains a `tabs` component ("free-trial toggle" design: OFF/ON tab
  stacks each holding a package stack and a purchase button).
- All experiments were run on throwaway duplicates created with
  `POST /v2/projects/{p}/paywalls/{id}/actions/duplicate` (since deleted).
  Writes used the public API v2 `PATCH /paywalls/{id}`
  (`{revision, components_config, components_localizations}`); reads used
  `GET /paywalls/{id}?expand=components`. The builder was cold-reloaded
  between steps.
- Runtime ground truth: the same `components_config` rendered via
  RevenueCatUI 5.76.0 (PaywallValidationTester harness) with intro-offer
  eligibility forced both ways.

## Findings matrix

Overrides present in `components_config` vs what the builder's rule list
shows after a cold reload:

| # | Override | Property | Condition form | Layer | Rule list | Rules preview | SDK runtime |
|---|---|---|---|---|---|---|---|
| 1 | pre-existing CTA label swap (x2, authored in builder ~June) | `text_lid` | legacy `intro_offer` | text inside tab stack | ✅ listed ("Modify layer / Text") | (n/a) | ✅ applied |
| 2 | builder-authored "Hide layer" (during experiment) | `visible` | extended `intro_offer_condition` | tabs component (top-level, picker-addressable) | ✅ listed, survives cold reload **and** an API identity-write | ✅ applied | ✅ applied |
| 3 | API-written show-when-eligible (`visible: false` base + `visible: true` override) | `visible` | legacy | stack inside tab stack | ❌ absent | ❌ not applied (base `visible:false` **is** honored, so the layer just looks gone in every preview state) | ✅ applied |
| 4 | same as #3 re-encoded | `visible` | extended | stack inside tab stack | ❌ absent | ❌ not applied | ✅ applied |
| 5 | API-written hide override | `visible` | extended | text inside tab stack | ❌ absent | ❌ not applied | ✅ applied |
| 6 | overrides from #1 re-encoded to extended form | `text_lid` | extended | text inside tab stack | ❌ absent (previously-listed rule disappears) | — | ✅ applied |

Control: `PATCH` writing the identical `components_config` back (identity
write) does **not** change what the rule list shows — the list is derived
from the component tree, not from separate builder-side state.

## Why this matters

1. **False negatives for humans:** a paywall can carry live conditional
   behavior (eligibility-dependent show/hide) that the builder presents as
   "no rules", and the builder's Introductory preview renders a state no real
   user sees.
2. **Combined with Part 1, there is no good path:** the rule can't be
   authored in the builder, and once written via the API it can't be seen,
   previewed, or edited there — teams must maintain it entirely outside the
   dashboard.
3. **Encoding fragility:** legacy vs extended condition encodings are each
   recognized in some contexts and not others, so API users can't pick one
   "builder-safe" form.

## Suggested fixes (any subset helps)

- Make the rule-list reverse-parser recognize visibility overrides on any
  layer (and both condition encodings), or at minimum surface an "unmanaged
  overrides exist on N layers" indicator instead of showing nothing.
- Let the rules preview evaluate all overrides the SDK evaluates.
- Allow the rule editor's layer picker to address components inside tab
  stacks (it already lists the tabs component itself).

## Repro (minimal)

1. Build a components paywall containing a `tabs` component with content in
   its tab stacks; publish.
2. `GET /v2/projects/{p}/paywalls/{id}?expand=components`; add to any stack
   inside a tab stack: `"visible": false` and
   `"overrides": [{"conditions": [{"type": "intro_offer_condition",
   "operator": "=", "value": true}], "properties": {"visible": true}}]`;
   `PATCH` it back as the draft.
3. Open the builder → Paywall logic: no Offer-type rule is listed; the rules
   preview shows the layer hidden in both Default and Introductory.
4. Render the same draft config with RevenueCatUI ≥ 5.62: the layer correctly
   hides/shows with intro-offer eligibility.
