# AGENTS.md — operating manual for the agent driving this lab

You are the operator. Humans describe what they want, review screenshots, and
approve. You do everything else with `python3 lab.py …`. Read this whole file once.

## Hard rules

1. **Never publish without explicit human approval in the current conversation.**
   A merged PR, an approved screenshot, "looks good" on a draft — none of that is
   publish approval. `publish` demands `--confirm PUBLISH`; only pass it when a human
   said "publish it" (record who/when in the variation's `NOTES.md`).
2. **Never author paywalls in the RevenueCat dashboard builder.** An open builder tab
   autosaves over API drafts; ask the human to close builder tabs before `push`.
3. **The dual-state, dual-platform screenshots are the source of truth.** The
   dashboard preview cannot evaluate every rule and shows fake prices.
4. **Base state = the trial-ineligible layout.** Old SDKs drop rules they don't know;
   the fallback must never promise a trial. `lint` warns when trial copy has no rule.
5. `push` is safe and repeatable (draft only). `publish` is the one consequential step.
   Rollback = push + publish the previous snapshot (`lab.py pull` keeps them).
6. Everything project-specific goes in `my/`. Never commit `my/.env`.

## First session in a fresh clone

```bash
python3 lab.py doctor                       # what's missing, with fix commands
python3 lab.py init --project proj...       # needs RC_API_V2_KEY (env or my/.env)
$EDITOR my/products.json                    # prices/periods/trials per package — REQUIRED
python3 lab.py detect-sdk <app dir> --apply # pin harnesses to the app's SDK versions
python3 lab.py status                       # live paywalls, drafts, local variations
```
`init` discovers paywalls/offerings/products via the API. If the API key lacks scopes,
ask the human for a secret key with paywall + offering + media read/write.
If the app dir isn't available, ask the human which SDK versions ship (React Native:
`react-native-purchases` → `purchases-hybrid-common` → native; `detect-sdk` does this hop).

**Expect long first builds and say so before running them:** iOS resolves
`purchases-ios` from GitHub (~1 GB clone, ~10 min, then cached); Android downloads
Gradle + dependencies (~5 min). Both look hung. Don't kill them.

## The loop

```bash
python3 lab.py new <name> --source published        # or draft | blank | <variation>
# edit my/variations/<name>/paywall.json  — or better, write generate.py (paywall_dsl.py)
python3 lab.py preview <name> [--generate] [--platform ios|android]
python3 lab.py lint <name>
python3 lab.py diff <name>                          # vs live published (or --against draft)
python3 lab.py upload-assets <name>                 # only if assets/ is used
python3 lab.py push <name> --yes                    # RevenueCat draft (never user-visible)
python3 lab.py publish --confirm PUBLISH            # ONLY on explicit approval
```

Screenshots land in `my/variations/<name>/screenshots/{ios,android}-{eligible,trial-used}.png`.
Show them to the human (upload/attach — don't describe them). Iterate on feedback in
the same variation; keep `NOTES.md` current (it is the approval record).

Prefer **generating** over hand-editing JSON for anything beyond small edits: start from
`--source blank` (a minimal `generate.py`: title, a card per package, CTA, footer links) or write one with `paywall_dsl.py` (iterate `products()` so it works
for any package set), then `preview --generate`. Raw JSON from `--source published`
is fine for small edits.

## When something looks impossible

- Component/JSON questions → `docs/PAYWALL_JSON.md` (field guide, vocab, overrides).
- "The builder doesn't show my rule" → `docs/revenuecat-builder-gaps.md` + the
  eligibility-siblings section of `docs/PAYWALL_JSON.md`. It's the builder, not you.
- API 422 → run `lint`; the rule is probably there. If not, fix it, add a lint rule,
  and `lab.py suggest` it.
- Layout differs between dashboard preview and SDK → the layout section of `docs/PAYWALL_JSON.md`.
- Harness build fails after an SDK bump → `docs/platforms.md` (compat matrix + known breaks).
- Emulator "offline" forever → we cold-boot (`-no-snapshot-load`) already; if a human
  started one with a stale snapshot, ask them to close it.

## A/B tests, targeting, new paywalls

- `create <variation> --title "…"` makes a brand-new paywall (unpublished draft, no
  offering) and registers it in `my/config.json`; use it instead of overwriting an
  existing paywall's draft when the work is a new design.
- Experiments compare *offerings*. The API can create offerings/packages, duplicate a
  paywall and attach it; **starting the experiment and targeting rules have no public
  API** — hand those two dashboard steps to the human with exact values.
- Don't trust an experiment dashboard's control-arm conversion numbers without a
  cross-check in your own analytics (documented under-attribution when the control is
  also the project default; see `docs/workflow.md`).

## Improving the lab

You will hit things this lab doesn't handle. Fix them locally in your fork, then
`python3 lab.py suggest --intent "…" --changes "…" --why "…" --open` — a prompt, not
a PR. Upstream generalizes it. Good candidates: a new lint rule, a DSL builder,
an SDK-version fix, a `doctor` check that would have saved you time.
After touching `lab.py`, `paywall_dsl.py`, or `lab_lint.py`, run
`python3 -m unittest` (seconds, no simulator) — then the four screenshots.
