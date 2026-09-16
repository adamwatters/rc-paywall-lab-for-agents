# Library

Reusable paywall knowledge for agents. Two tiers:

- **designs/** — complete, parameterized paywalls (`generate.py` + README +
  screenshots for both platforms and both eligibility states). Start one with
  `python3 lab.py new <name> --source <design>`.
- **recipes/** — the non-obvious building blocks, each a `paywall_dsl` function plus
  a short doc with the production lesson behind it.

`catalog.json` is the machine-readable index (tags → entries).

## Designs

| design | tags | one-liner |
|---|---|---|
| [gradient-trial-toggle](designs/gradient-trial-toggle/) | trial-forward, toggle, two-tier, gradient, social-proof, eligibility-aware | mesh gradient, photo strip + quote, free-trial switch over plan cards |
| [minimal-two-tier](designs/minimal-two-tier/) | minimal, no-image, starter, eligibility-aware | white, headline + 3 benefits + cards + CTA; the base to paste a mock into |

## Recipes

| recipe | when you need it |
|---|---|
| [eligibility-siblings](recipes/eligibility-siblings.md) | any paywall that mentions a trial (hide it honestly for ineligible users, visibly in the builder) |
| [trial-toggle](recipes/trial-toggle.md) | the "Not sure yet? Start free trial" switch |
| [badge-overlay](recipes/badge-overlay.md) | "7 DAYS FREE" / "MOST POPULAR" pills on cards |
| [responsive-column](recipes/responsive-column.md) | layouts that match the dashboard preview and fit small phones |
| [local-assets](recipes/local-assets.md) | images: local preview, the 5-URL rule, composites, upload before push |
| [copy-variables](recipes/copy-variables.md) | prices/periods in copy without hardcoding |
| [localization-ids](recipes/localization-ids.md) | the 10-char lid rule and copy management |

## Contributing a design or recipe

Don't send a PR — send a **prompt**: `python3 lab.py suggest --open` (or an issue)
describing what you built and why it generalizes; attach screenshots. Upstream
turns it into a generalized entry. See [CONTRIBUTING.md](../CONTRIBUTING.md).
