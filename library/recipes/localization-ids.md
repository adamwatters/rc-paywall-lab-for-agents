# Recipe: localization ids and copy management

Every visible string is a `text_lid` into `components_localizations.<locale>`.
The API only accepts ids that are **exactly 10 chars of `[A-Za-z0-9_-]`** (HTTP 422
otherwise). `paywall_dsl.lid("readable_name")` derives one deterministically, and
`Strings.add(key, text)` keeps the copy bag in one place:

```python
S = Strings()
title = text(S.add("title", "Unlock everything"), fsize=28)
```

- Reuse a lid wherever the same copy appears (siblings, tabs) so edits propagate.
- URLs for Terms/Privacy links are localized strings too (`navigate_action(url_lid)`).
- Text overrides (`when({"type": "intro_offer"}, text_lid=other)`) in the legacy
  condition form are the one kind of nested rule the dashboard builder does list.
- `lab.py lint` flags unknown, malformed, and unused ids.
