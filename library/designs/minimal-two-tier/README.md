# minimal-two-tier

**The clean starting point: no images, one column, a card per package.** Headline,
three benefit rows, package cards, CTA, fine print, footer links.

| tags | minimal · no-image · starter · eligibility-aware |
|---|---|
| eligibility | headline via siblings recipe; CTA label via a text override (`intro_offer` → "Start free trial") |
| layout | single full-height column with two spacers |
| assets | none |
| products | one card per package in `my/products.json`; first = selected |

Use it: `python3 lab.py new my-first --source minimal-two-tier` then
`python3 lab.py preview my-first --generate`. Good base for pasting a mock's copy in.
