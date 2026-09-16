# Recipe: local assets, composited art, and the 5-URL rule

**Local preview.** Reference images as `https://assets.pawwalls.com/lab/<file>` (the
DSL's `image()` / `image_background()` do this) and put the file in
`<variation>/assets/`. Both harnesses rewrite that host to the local mirror.

**Every image source needs all five URL fields** — `original`, `heic`, `heic_low_res`,
`webp`, `webp_low_res` — plus integer `width`/`height`. The API rejects sources
without them and Android's decoder throws on missing webp fields (iOS is lenient,
which is how this bites cross-platform). Pointing all five at one PNG is fine; the
SDKs sniff the real format. `lab.py lint` enforces it.

**Composited effects** (rotated/fanned photos, baked shadows, mesh gradients) aren't
component features — pre-render them into one asset. `paywall_dsl.write_png` /
`mesh_gradient` make placeholder art with the stdlib; replace with real exports.

**Before push**, `lab.py upload-assets <name>` sends each file to RevenueCat's media
library and records hosted URLs in `uploaded_assets.json`; `push`/`create` substitute
them automatically and refuse if anything is unmapped. Export @2x/@3x for crispness
(the `width`/`height` you declare are the file's pixel size; `display_w/h` are points).
