# Recipe: product variables in copy

Text is resolved per package at render time. Use these instead of hardcoding prices
(a hardcoded "$5/month" silently goes stale when the price changes):

| variable | example |
|---|---|
| `{{ product.price }}` | $59.99 |
| `{{ product.price_per_month }}` | $4.99 |
| `{{ product.price_per_period }}` | $59.99/yr |
| `{{ product.period }}` / `{{ product.periodly }}` | year / yearly |
| `{{ product.period_in_months }}` | 12 |
| `{{ product.offer_period }}` | 7 days |
| `{{ product.store_product_name }}` | Annual |
| `… | capitalize` | Yearly |

The period words come from `ui_config.localizations` (already in `my/ui_config.json`).
Rounding isn't available: `$59.99/12` renders `$4.99`, not `$5`. If a mock demands
`$5/month`, that's a hardcoded string with a maintenance note.

Constants in the DSL: `V_PRICE`, `V_PRICE_PER_MONTH`, `V_PERIOD_MONTHS`, …
