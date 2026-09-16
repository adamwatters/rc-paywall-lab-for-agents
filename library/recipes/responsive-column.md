# Recipe: one full-height column with spacers (no sticky footer)

Layout that renders identically in the SDK, in the dashboard preview, and on small
phones without scrolling:

```python
content = stack([spacer(), headline, spacer(), social_proof, spacer(), offers, links],
                h="fill", margin=edges(top=44, leading=16, trailing=16, bottom=30))
```

Why, learned the hard way:
- **The dashboard preview and the SDK disagree about sticky footers.** The preview
  overlays the footer on a full-height content area; the SDK stacks it below. A
  footer + flexible content looked fine in the SDK and overlapped in the dashboard on
  every device size. A single column has no such split.
- **`distribution: space_evenly` counts hidden children.** The SDK inserts a flex gap
  per child even for `visible: false` ones, so the two eligibility states spaced
  differently. Explicit `spacer()` stacks (fill-height, empty) don't.
- **Content ignores the top safe area** — use a fixed top margin (44pt clears the
  Dynamic Island) and a bottom margin for the home indicator.
- Group things that must stay together (photo + quote) in one stack with a fixed gap;
  put spacers only between groups.

Check on a small device too (`ios.device_name: "iPhone SE (3rd generation)"` in
`my/config.json`; the harness needs iOS ≥ 18.5 runtimes).
