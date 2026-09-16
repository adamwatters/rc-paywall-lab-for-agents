# gradient-trial-toggle

**Trial-forward paywall on a mesh gradient, with a free-trial switch.** Headline,
social proof (photo tiles + quote), then the offer block: "Not sure yet? Start free
trial" switch over the plan cards and CTA. Trial-ineligible users get an honest
variant with no trial copy at all.

| tags | trial-forward · toggle · two-tier · gradient · social-proof · eligibility-aware |
|---|---|
| eligibility | builder-legible siblings (headline pair, switch vs plain offers) |
| layout | single full-height column, explicit spacers, no sticky footer — same render in SDK, dashboard preview, and on small phones |
| assets | `bg.png` (generated mesh gradient), `photo_strip.png` (generated tiles) — replace with your own |
| products | one card per package in `my/products.json`; first = selected; trial length from it |
| origin | adapted from a shipped design (Sept 2026); copy and art are placeholders |

Use it: `python3 lab.py new my-gradient --source gradient-trial-toggle` then edit
`generate.py` (copy at the top, palette constants) and `python3 lab.py preview my-gradient --generate`.

Recipes used: [eligibility-siblings](../../recipes/eligibility-siblings.md),
[trial-toggle](../../recipes/trial-toggle.md), [badge-overlay](../../recipes/badge-overlay.md),
[responsive-column](../../recipes/responsive-column.md), [local-assets](../../recipes/local-assets.md).
