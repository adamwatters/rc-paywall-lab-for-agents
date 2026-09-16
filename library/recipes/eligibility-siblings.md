# Recipe: eligibility siblings (builder-legible show/hide)

**Problem.** A paywall that promises a free trial lies to users who already used
theirs (Apple/Google won't grant another; they're charged immediately). The SDK's
`intro_offer` rules can hide trial copy, but the dashboard builder's rules UI can
only *see* visibility rules on **top-level** layers, not on anything nested inside a
`tabs` component — precisely where toggle-style paywalls keep their trial copy. Rules
written there work in the app but are invisible in the builder (we measured this:
[docs/revenuecat-builder-gaps.md](../../docs/revenuecat-builder-gaps.md)).

**Pattern.** Two sibling layers at the same level:

```
Content
├── Headline (trial)     base hidden,  SHOWN when intro offer available
├── Headline (no trial)  base visible, HIDDEN when intro offer available
…
├── Switch (tabs)        base hidden,  SHOWN when intro offer available
└── Offers (no trial)    base visible, HIDDEN when intro offer available
```

- Base state = the trial-INELIGIBLE layout. Old SDKs that don't understand the rule
  (or `visible`) render the honest version, or both siblings — never a false promise.
- Use the extended condition encoding (`intro_offer_condition`, operator `=`, value
  `true`); it's what the builder's rule scanner recognizes on top-level layers.
- Share text lids between the siblings where copy is identical so edits stay single-sourced.

**DSL.**
```python
trial, plain = eligibility_siblings(trial_node, no_trial_node)   # mutates + returns both
```
Both seed designs use it. Cost: a duplicated subtree in JSON (generated, so free to maintain).

**Verify** with `lab.py preview` — both states on both platforms are the review surface.
The dashboard's Introductory preview only evaluates the rules it can list.
