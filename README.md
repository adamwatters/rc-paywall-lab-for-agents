# rc-paywall-lab-for-agents

**Author, preview, lint, and ship RevenueCat paywalls as code — offline, on the iOS
simulator and Android emulator, driven by a coding agent.** No dashboard builder.

RevenueCat Paywalls v2 are JSON ("components"). This lab lets an agent (Claude
Code, Codex, Cursor, …) write that JSON from Python, render it with the *exact*
`purchases-ios` / `purchases-android` versions your app ships — in both
intro-offer eligibility states, with your real prices mocked — diff it against
production, push it as a draft through the RevenueCat REST API v2, and publish only
when a human says so. The non-obvious rules (eligibility rules the builder can't
express, layout parity gotchas, the API's undocumented validation rules) are encoded
in lint and the field guide so agents don't rediscover them.

```
idea ──▶ generate.py ──▶ paywall.json ──▶ lab.py preview ──▶ 4 screenshots ──▶ human review
                                              (iOS + Android × eligible / trial-used)      │ approve
                                 RevenueCat draft ◀── lab.py push ◀── lab.py lint ◀────────┘
                                        │  human-approved `lab.py publish`
                                      LIVE
```

## 60-second start (agents: read [AGENTS.md](AGENTS.md) — it is the operating manual)

```bash
git clone https://github.com/adamwatters/rc-paywall-lab-for-agents.git paywall-lab
cd paywall-lab
export RC_API_V2_KEY=sk_...              # RevenueCat secret API key (or put it in my/.env)
python3 lab.py init --project proj...    # writes my/config.json + my/products.json from your project
$EDITOR my/products.json                 # prices / periods / trials (the API doesn't know store prices)
python3 lab.py detect-sdk ../your-app --apply   # pin both harnesses to the SDK versions your app ships
python3 lab.py doctor                    # toolchain check with exact fix commands
python3 lab.py new first --source published
python3 lab.py preview first             # first run builds the harnesses (iOS ~10 min, Android ~5 min), then ~1 min
```

Look at `my/variations/first/screenshots/`. Then `lint`, `push --yes`, and — with
explicit approval — `publish --confirm PUBLISH`.

Requirements: Python 3.9+ (no packages), Xcode + an iOS simulator for iOS, a JDK
17+ and Android SDK with an AVD for Android. Either platform alone works
(`platforms` in `my/config.json`).

## What's in the box

| | |
|---|---|
| `lab.py` | the CLI: `doctor`, `detect-sdk`, `init`, `status`, `pull`, `new`, `render`, `preview`, `diff`, `lint`, `upload-assets`, `push`, `create`, `publish`, `suggest` |
| `paywall_dsl.py` | build paywall JSON from Python; includes higher-level builders (`eligibility_siblings`, `trial_toggle`, `badge_overlay`, `footer_links`, …) |
| `lab_lint.py` | every API/SDK rule that has rejected or mis-rendered a paywall on us, as checks |
| `harness/ios` | Xcode app + SwiftPM dependency on `purchases-ios` (version = one line); renders offline with injected eligibility |
| `harness/android` | Gradle app + Maven `purchases-ui` (version = one line); public opt-in APIs only |
| `docs/` | the components JSON field guide, the dashboard-builder gaps report, platform notes, workflow & policy |
| `tests/` | `python3 -m unittest` — DSL→lint contract, every lint rule, `render` output, `init`/`detect-sdk` from fixtures; no simulator needed (runs in CI) |
| `my/` | **your** project: config, products, variations, snapshots (a fork keeps these; upstream never touches them) |

## Why this exists

- **The dashboard builder can't express or even display some rules** (visibility rules
  inside toggle designs), its preview uses fake prices and different footer semantics
  than the SDK, and an open builder tab silently autosaves over API-written drafts.
  Measured, documented: [docs/revenuecat-builder-gaps.md](docs/revenuecat-builder-gaps.md).
- **Only published paywalls reach the SDK**, so previewing a draft in a real app is
  impossible. The harnesses load JSON straight into RevenueCatUI instead.
- **Paywall work is iterative and visual** — exactly what an agent with a simulator
  and a screenshot loop is good at, once the environment stops fighting it.

## Contributing: send prompts, not PRs

Fork it, keep your `my/` in your fork, `git pull upstream main` for tool updates.
When you build something others would want — a lint rule, a DSL builder, a
platform fix — run `python3 lab.py suggest --open` (or open an issue) describing the
**intent**. Upstream turns it into a generalized change. See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT. Not affiliated with RevenueCat. The iOS loader is adapted from RevenueCat's
MIT-licensed `PaywallPreviewResourcesLoader`.
