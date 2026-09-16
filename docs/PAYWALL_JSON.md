# Paywall JSON field guide (RevenueCat Paywalls v2 "components")

What the SDKs decode (`purchases-ios` `Sources/Paywalls/Components/*`,
`purchases-android` `purchases/.../paywalls/components/*`) and what the API v2
accepts. Learned from the SDK sources and from shipping. `paywall_dsl.py` emits all
of these shapes; `lab_lint.py` enforces the rules marked ⚠️.

A variation's `paywall.json`:

```json
{
  "components_config":        { "base": { "background", "header", "stack", "sticky_footer" } },
  "components_localizations": { "en_US": { "<lid>": "string" } },
  "default_locale": "en_US",
  "revision": 1,
  "automatically_scale_font_size": true
}
```

All keys snake_case. Unknown keys are ignored by the SDKs — don't rely on it.

## The base

- `background`: `{"type": "color", "value": <color>}` or
  `{"type": "image", "value": <image source>, "fit_mode": "fill", "color_overlay": null}`.
- `header`: optional stack above the content (usually `null`).
- `stack`: the root content stack (scrollable if taller than the screen).
- `sticky_footer`: `null` or `{"type": "footer", "id", "name", "stack"}` ⚠️ the type
  name is `footer`, not `sticky_footer` (API 422). Prefer no footer — see the
  responsive-column recipe: the dashboard preview and the SDK lay footers out differently.

## Components (every component has `type`, `id`, `name`)

- **stack** — flex-like container. `dimension` = `{type: vertical|horizontal|zlayer,
  alignment, distribution}` (distribution: start|center|end|space_between|space_around|
  space_evenly), `components[]`, `size` (`{width, height}` each `{type: fill|fit|fixed,
  value}`), `spacing`, `padding`/`margin` (top/leading/bottom/trailing), `background`
  (`{type: color, value}` or image), `background_color`, `shape` (`{type: rectangle,
  corners: {…}}` or `{type: pill, corners: null}`), `border` (`{color, width}`),
  `shadow`, `badge` (`{style: overlay, alignment, stack}`), `visible`, `overrides`.
- **text** — `text_lid`, `color`, `background_color`, `font_name` (alias), `font_size`,
  `font_weight` (regular…black) + `font_weight_int`, `horizontal_alignment`, `size`,
  `padding`, `margin`.
- **image** — `source` (`{light: <image source>, dark?}`), `size`, `fit_mode` (fit|fill),
  `mask_shape`, `color_overlay`, `border`, `shadow`. Image source = ⚠️ **all five** of
  `original`, `heic`, `heic_low_res`, `webp`, `webp_low_res` + integer `width`/`height`.
- **icon** — named icon from `https://icons.pawwalls.com` (`formats` per theme), `color`, `size`.
- **package** — `package_id` (`$rc_annual`, `$rc_monthly`, `$rc_three_month`, …, or a
  custom identifier), `is_selected_by_default`, `stack`. Text inside resolves product
  variables against this package.
- **purchase_button** — the CTA; `stack` holds its label.
- **button** — `action`: `{type: restore_purchases}` or `{type: navigate_to, destination:
  terms|privacy_policy|url, url: {method: external_browser, url_lid}, sheet: null}`.
- **tabs** — `control` (`{type: toggle, stack}` with a `tab_control_toggle` component:
  `default_value`, `thumb_color_*`, `track_color_*`), `tabs[]` (`{type: tab, id, name,
  stack}`), `default_tab_id`. A `tab_control` component inside a tab renders the switch there.
- **carousel** — `pages[]` of stacks + page-control settings.
- **timeline**, **video** — exist; not covered here.

## Colors

`{"light": {"type": "hex", "value": "#RRGGBBAA"}, "dark": {…}}` (`dark` optional) or a
gradient `{"type": "linear", "degrees", "points": [{"color", "percent"}]}`. Named colors:
`{"type": "alias", "value": "<name>"}` via `ui_config.app.colors`.

## Localization

Every visible string is a `text_lid` (and link URLs are `url_lid`s) into
`components_localizations.<locale>`. ⚠️ ids are exactly 10 chars of `[A-Za-z0-9_-]`.
Product variables: `{{ product.price }}`, `{{ product.price_per_month }}`,
`{{ product.period }}`, `{{ product.periodly }}`, `{{ product.period_in_months }}`,
`{{ product.offer_period }}`, `{{ product.store_product_name }}` (+ `| capitalize`).
Period words come from `ui_config.localizations`.

## Overrides (rules)

```json
"overrides": [{ "conditions": [{"type": "intro_offer_condition", "operator": "=", "value": true}],
                "properties": { "visible": true } }]
```

Conditions: `intro_offer` (legacy form), `intro_offer_condition` (extended form with
operator/value), `promo_offer`, `selected` (package selected), `compact`/`medium`/
`expanded` (size classes). Properties = any of the component's visual properties
(`visible`, `text_lid`, `color`, `background`, `border`, …). Unknown condition types
make old SDKs skip the override → **author the base state as the safe fallback.**

Eligibility ground truth: iOS asks StoreKit per subscription group per Apple ID
(`unknown` renders as eligible); Android derives it from the product's offer phases
(a free-trial phase present = eligible). `lab.py preview` forces both states.

## UI config (fonts, named colors)

`font_name: "serif"` resolves through the project UI config's `app.fonts.serif`, which
needs a face per platform: `{"ios": {"type": "name", "value": "Georgia"}, "android":
{"type": "name", "value": "serif"}}` (or `type: google_fonts`, or an uploaded custom
font). `my/ui_config.json` supplies this for previews; production needs the alias
registered with RevenueCat or users get the system font.

## Dashboard / API facts that matter

- `GET /projects/{p}/paywalls/{id}?expand=components` → `{components: {draft|null,
  published}}`. `draft: null` = no unpublished changes.
- `PATCH /paywalls/{id}` `{revision, components_config, components_localizations?}` —
  `revision` must match the current draft's (or published's when draft is null); stale
  writes 409. `POST …/actions/publish`, `…/unpublish`, `…/duplicate`; `POST /paywalls`
  creates; `POST /media_assets` uploads images (base64) and returns hosted formats.
- ⚠️ **An open dashboard builder tab autosaves over API drafts.** Close them before `push`.
- Dashboard previews render the base state with RC's sample products (fake prices) and
  only the rules their scanner can list. See `revenuecat-builder-gaps.md`.
