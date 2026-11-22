# edgereckon

**The code-graph auditor: verified-or-refuse for call graphs.**

AI coding agents now navigate codebases by knowledge graphs — tools
with a combined ~500K GitHub stars build call graphs from parsing and
present every edge to the agent as fact. None of them measures
whether the edges are *true*. The static-analysis literature says
they predictably are not: measured against dynamic ground truth,
static call-graph tools have missed on average 61% of executed
methods on framework-heavy code (Samhi et al., ISSTA 2024), because
the target of a call in modern code is often decided at runtime —
registries, DI containers, decorator registries, string routing,
monkey-patching.

edgereckon audits the graph an agent is about to trust. It checks the
graph's call edges against independent ground truth obtained offline
— **execution traces from the target repo's own test suite**, run
under `sys.settrace` — plus an independent `ast` census of the
worktree, and stamps every edge:

- **VERIFIED** — the call was actually observed at runtime.
- **REFUTED** — the evidence positively contradicts the edge: the
  claimed target does not exist in the worktree, or the trace proves
  the call binds to a different symbol of the same name.
- **UNVERIFIABLE** — not observed and not refutable. Absence of
  observation is *never* treated as refutation: an unobserved edge
  may be an untested path, and edgereckon says which evidence is
  missing instead of guessing.

It then publishes the graph's measured **precision/recall**, runs a
**drift check** (the graph's recorded source hashes vs the current
worktree), and answers impact questions — *"what breaks if I change
X?"* — **only over the verified subgraph**, returning the rest as a
refused remainder with machine-readable reason codes.

Pure Python standard library. Offline. No model calls.

## Quick start

```bash
# 1. Audit the graph edgereckon builds itself for a Python repo
python3 -m edgereckon audit --repo /path/to/repo --out report.json

# 2. Or audit an existing Graphify graph.json
python3 -m edgereckon audit --repo /path/to/repo \
    --graph graph.json --out report.json

# 3. Ask what breaks -- answered over verified edges only
python3 -m edgereckon impact --report report.json \
    --symbol shop.pricing:compute_tax
```

`build` writes the self-built static graph on its own; `audit`
without `--graph` builds and audits in one step. Ground truth uses
stdlib `unittest` discovery (`--test-dir`, default `tests`); a repo
whose suite cannot run that way is reported NO_GROUND_TRUTH, never
silently passed.

## Reading a report

```
claimed call edges: 13
  VERIFIED:     8
  REFUTED:      3
  UNVERIFIABLE: 2
precision (decidable edges): 0.727
verified share of claimed:   0.615
recall vs traced pairs:      0.381 (8/21)
```

- **Precision (decidable)** = VERIFIED / (VERIFIED + REFUTED) — over
  the edges the evidence could actually decide.
- **Verified share** = VERIFIED / all claimed edges.
- **Recall** = traced caller→callee pairs (both endpoints defined in
  the worktree) that the graph claims, over all such traced pairs.
  Traces prove presence only, so recall is measured against what the
  tests executed; the report states the trace's coverage of the
  repo's symbols alongside it. A low recall against a thin test suite
  says as much about the suite as about the graph.

Reason codes you will see: `OBSERVED`, `CALLEE_NOT_FOUND`,
`CALLER_NOT_FOUND`, `WRONG_SYMBOL`, `TARGET_OUTSIDE_REPO`,
`NO_GROUND_TRUTH`, `CALLER_NOT_EXECUTED`, `CALLEE_NOT_EXECUTED`,
`NOT_OBSERVED`; for impact: `UNVERIFIED_EDGE`, `DRIFTED_FILE`,
`NO_GROUND_TRUTH`, `NO_SUCH_SYMBOL`, `AMBIGUOUS_SYMBOL`.

## The fixture

[`fixtures/hazards_repo/`](fixtures/hazards_repo/) is a small package
with planted, labelled hazards — registry/dict dispatch, a DI
container, a decorator registry, string-based routing,
monkey-patching, name shadowing — where the correct verdicts are
known in advance, so the auditor is itself tested against ground
truth about ground truth. Highlights from the shipped audits:

- The self-built static graph: 15 claimed edges, **13 VERIFIED,
  0 REFUTED, 2 UNVERIFIABLE**, recall **0.619** — every dynamic edge
  (dispatch, DI, decorator registry, routing) is a measured recall
  miss, and the monkey-patched edge is honestly UNVERIFIABLE, never
  stamped verified.
- A hand-written Graphify-format graph claiming the dynamic edges
  plus three planted errors: **8 VERIFIED, 3 REFUTED** (a phantom
  target, a stale target, a wrong-symbol resolution), **2
  UNVERIFIABLE**, precision 0.727 on decidable edges.
- Impact on `shop.pricing:compute_tax` returns the verified callers
  and refuses `express_total`'s edge with its reason code, marking
  the answer incomplete rather than whole.

## Trust model (read this before trusting it)

- **A trace proves presence, not absence.** VERIFIED means "this
  call executed under this test run". UNVERIFIABLE is the honest
  stamp for everything else the trace cannot settle; REFUTED is
  reserved for positive contradiction.
- **Ground truth is the repo's own test suite.** If the tests are
  thin, the audit says so (coverage is printed). If they cannot run
  under stdlib `unittest` discovery, the audit reports
  NO_GROUND_TRUTH and impact queries refuse outright.
- **The static builder is deliberately simple.** edgereckon audits
  graphs; it does not compete as a graph builder. Its own graph's
  recall misses are part of the demonstration.
- **Drift is only as good as the hashes.** Self-built graphs carry
  per-file SHA-256 build state. Ingested graphs without source
  hashes report drift UNKNOWN / NO_PROVENANCE — never "clean".
- **What v1 does not do:** non-Python repos; pytest-native test
  suites (see above); CodeGraph/GitNexus export formats; a full
  second call-graph extraction (the independent census powers
  existence refutation; it is not a second graph). The coverage
  statement in `validate.py` lists exactly what v1 implements.

## Development

```bash
python3 validate.py   # full test suite + CLI fixture checks; exit 0 = green
```

## License

MIT. See [LICENSE](LICENSE). Name-collision record:
[NAME_CHECK.md](NAME_CHECK.md). Compliance record:
[COMPLIANCE.md](COMPLIANCE.md).
