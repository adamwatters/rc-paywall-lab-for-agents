# Contributing — send prompts, not PRs

This repo is meant to be **forked** and driven by an agent. Your fork holds your
project's state in `my/`; the tool code is generic. Pull upstream for updates.

When you (or your agent) improve something that others would want, **don't open a
PR**. Open a **prompt**: an issue that states the *intent*, what you changed locally,
why it generalizes, and evidence. Upstream (also an agent, supervised) turns prompts
into generalized changes so everything stays coherent and easy to maintain.

```bash
python3 lab.py suggest \
  --intent  "Lint should catch X because the API rejects it with 422 …" \
  --changes "added rule to lab_lint.py; fixture in my/variations/foo" \
  --why     "any paywall using Y hits this" \
  --evidence "API error text / screenshot paths / SDK 5.80.0" \
  --open      # opens the issue via gh; omit to just print it
```

Good prompts:
- a lint rule (with the rejection text it prevents)
- a DSL builder (a reusable element + the lesson behind it), with screenshots for
  both platforms and both eligibility states — no brand assets, no product ids
- a `doctor` check or platform fix (with the SDK/OS versions involved)
- a doc correction with the source

Upstream verifies every change with `python3 -m unittest` (CI) and the four
screenshots (both platforms × both eligibility states, manual).

License: MIT. By submitting a prompt you agree the resulting change is MIT.
