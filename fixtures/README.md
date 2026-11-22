# fixtures

- `hazards_repo/` — a small Python package with planted, labelled
  call-graph hazards (registry/dict dispatch, a DI container, a
  decorator registry, string-based routing, monkey-patching, name
  shadowing) and a `unittest` suite that serves as the trace
  ground-truth instrument. See `hazards_repo/README.md` for the
  hazard table and the known-correct verdicts.
- `graphify_hazards.json` — a hand-written graph in Graphify's
  node-link `graph.json` format claiming edges over `hazards_repo`,
  including three planted errors: a phantom target
  (`pricing.apply_discount`, never existed), a stale target
  (`shop.legacy:charge_card`, file gone), and a wrong-symbol
  resolution (`render -> shop.pricing:format_price`, where the trace
  proves the call binds to `shop.report`'s local `format_price`).

Both fixtures were written for this project; no third-party code or
data is included.
