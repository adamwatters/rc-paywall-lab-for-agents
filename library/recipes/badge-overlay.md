# Recipe: badge overlay on a card

A pill floating over a card's top edge ("7 DAYS FREE", "MOST POPULAR"). It's the
stack's `badge` property with `style: overlay`; alignment `top_trailing` /
`top_leading` / `top`.

```python
card = stack([...], badge=badge_overlay(S.add("badge", "7 DAYS FREE"),
                                        gradient(90, [("#FE6D5Bff", 0), ("#FE4F63ff", 100)])))
```

Gotcha: the badge is part of the card, so a badge that should only show in one state
(e.g. only when the trial switch is ON) belongs on the copy of the card in that tab —
not an override. Cards are cheap to duplicate in a generator.
