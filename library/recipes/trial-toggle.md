# Recipe: free-trial switch (tabs component)

The "Not sure yet? Start free trial" row with a switch. It's a `tabs` component whose
control is a `toggle`; each tab holds its own copy of the offer block (OFF: plain
cards + "Continue"; ON: trial badges + "Continue for free"). A `tab_control()`
placeholder inside each tab's row is where the switch renders.

```python
switch = trial_toggle([toggle_row()] + offers(False, cta),           # OFF tab
                      [toggle_row()] + offers(True, cta_trial),      # ON tab
                      track_on=BRAND, default_on=False)
```

Notes from production:
- Default OFF vs ON was A/B tested (Aug–Sep 2026, ~1,000 exposures/arm): **no lift**
  from default ON on trial starts or paid conversion; keep OFF unless you have a reason.
- Both tabs sell the same products, so an OFF-tab purchase still gets the trial when
  the store grants one — the toggle is presentation, not a different offer.
- Pair it with [eligibility-siblings](eligibility-siblings.md): hide the whole switch
  for trial-ineligible users and show a plain offers stack instead.
