# hazards_repo — the planted-hazard fixture

A tiny Python package (`shop/`) plus a `unittest` suite (`tests/`)
whose call structure is deliberately hazardous for static call
graphs. Every hazard is planted, and the correct audit verdicts are
known in advance — this fixture is ground truth about ground truth,
used to test the auditor itself.

| Hazard | Where | What the static graph does | Correct audit outcome |
|---|---|---|---|
| Registry / dict dispatch | `shop/dispatch.py` | sees no edge out of `notify()` (or naively claims all registry values) | `notify -> send_email` VERIFIED (traced); `notify -> send_sms` UNVERIFIABLE when claimed (callee never executed) |
| DI container | `shop/container.py` | sees class instantiation in `build_checkout()`, misses the wired call | `CheckoutService.checkout -> TaxService.tax` is a recall miss for the static graph; VERIFIED for any graph that claims it |
| Decorator registry | `shop/events.py` | cannot see `emit -> handle_ping` | recall miss for the static graph; VERIFIED when claimed |
| String-based routing | `shop/routes.py` | cannot see `route -> home_page` | recall miss for the static graph; VERIFIED when claimed |
| Monkey-patching | `shop/checkout.py` + tests | claims `express_total -> pricing.compute_tax` | UNVERIFIABLE / NOT_OBSERVED — the edge is only ever run patched, so it must never stamp VERIFIED |
| Name shadowing | `shop/report.py` | (external graph) resolves `render`'s call to `shop.pricing:format_price` | REFUTED / WRONG_SYMBOL — the trace proves the local symbol is invoked |
| Phantom / stale targets | `../graphify_hazards.json` only | claims `pricing.apply_discount` (never existed) and `shop.legacy:charge_card` (file gone) | REFUTED / CALLEE_NOT_FOUND |

The plain chain `receipt -> total_with_tax -> pricing.compute_tax`
and `receipt -> pricing.format_price` is the control case: claimed
and traced, so VERIFIED.
