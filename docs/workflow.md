# Workflow & policy: local → draft → published

| World | What | Who sees it | Command |
|---|---|---|---|
| **Local** | `my/variations/<name>/` JSON + assets rendered by the harnesses | you | `preview` |
| **Draft** | the paywall's unpublished server-side copy at RevenueCat | dashboard viewers only, never the app | `push --yes` / `create` |
| **Published** | what every user's SDK downloads | everyone | `publish --confirm PUBLISH` (human-approved) |

`push` is safe and repeatable; it overwrites the draft (revision-guarded against
concurrent edits). `publish` is the one consequential step. Rollback = push + publish
the previous snapshot (`pull` keeps them in `my/snapshots/`).

## Publish policy (copy into your team's rules)

- Publishing requires **explicit human approval in the current conversation**
  ("publish it"). Approved screenshots, a merged PR, or "looks good" on a draft are not
  approval. Record who approved and when in the variation's `NOTES.md`.
- Never author in the dashboard builder; close builder tabs before `push`.
- If an A/B test is running, mirror changes to both arms' paywalls (or deliberately
  hold) so the test stays clean.

## Production-parity checklist before publish

1. `lint` clean (lids, image URL fields, footer type, fonts).
2. Local images uploaded (`upload-assets`) — push substitutes hosted URLs and refuses otherwise.
3. Font/color aliases registered in the RevenueCat project (unregistered aliases fall
   back to the system font silently).
4. Both platforms × both eligibility states reviewed by a human.
5. `diff` shows exactly the intended change vs live.

## New paywalls, experiments, targeting

- `create <variation> --title "…"` makes a **new** paywall as an unpublished draft (no
  offering) and registers it in `my/config.json`; attach an offering with `--offering`.
- Experiments compare *offerings*. The API can create offerings and packages, duplicate a
  paywall and attach it; **starting an experiment and targeting rules have no public
  API** — those are two dashboard steps for the human.
- QA on a real account: `POST /customers/{id}/actions/assign_offering` pins a test user
  to an offering (TestFlight/internal-testing verification).
- Don't trust an experiment dashboard's control-arm conversion numbers without a
  cross-check in your own analytics. Observed (Aug 2026): control-arm trial→paid
  reported ~2.5× lower than the same population in webhook-fed analytics and in
  RevenueCat's own Charts API; the treatment arm reconciled fine. Likely cause: the
  control offering was also the project default, shared with non-enrolled traffic.

## Fork hygiene

Your fork = tool + your `my/`. Upstream never touches `my/`; `git pull upstream main`
merges cleanly. Commit variations, screenshots, snapshots. Never commit `my/.env`.
