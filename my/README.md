# my/ — your project's state

Everything specific to *your* RevenueCat project lives here, so the tool code
above stays generic and `git pull`/merges from upstream never touch your work.

| File / dir | What | Commit it? |
|---|---|---|
| `config.json` | project id, paywall registry, simulator/emulator settings | yes (no secrets in it) |
| `products.json` | your packages with price / period / trial per platform (the harnesses mock products from this) | yes |
| `ui_config.json` | font/color aliases for local previews (+ variable period words) | yes |
| `variations/<name>/` | one paywall change: `paywall.json` (or `generate.py`), `NOTES.md` (approval record), `screenshots/`, optional `assets/` | yes |
| `snapshots/` | `lab.py pull` copies of live configs (rollback source) | yes |
| `.env` | `RC_API_V2_KEY=sk_...` | **never** (gitignored) |
| `.resources/` | rendered simulator input (regenerated) | never (gitignored) |

Bootstrap: `python3 lab.py init --project proj...` writes `config.json` and a
`products.json` skeleton; edit prices, then `python3 lab.py doctor`.
`PAYWALL_LAB_HOME=/elsewhere` relocates this whole directory (e.g. into your app repo).
