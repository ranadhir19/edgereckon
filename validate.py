#!/usr/bin/env python3
"""Validation harness for edgereckon.

Runs the full unit test suite (which audits the planted-hazard
fixture, whose correct verdicts are known in advance), then an
end-to-end CLI check: build -> audit (self-built graph) -> audit
(Graphify-format graph) -> impact, asserting the headline stamp
counts in the JSON reports. Exit 0 only if everything passes.
Failures are fixed in the code, never by weakening these checks.

The coverage statement at the end is part of the deliverable: it
states honestly which of the landscape scan's Position 1 claims
v0.1.0 implements, which are partial, and which are not in v1.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

COVERAGE_STATEMENT = """\
== coverage statement: scan Position 1 claims vs v1 ==
IMPLEMENTED (7):
  1. Ingest Graphify-format graph.json behind the internal edge format.
  2. Self-built static graph for Python repos (stdlib ast; functions,
     classes, methods as nodes; resolvable call edges).
  3. Per-edge stamps VERIFIED / REFUTED / UNVERIFIABLE with
     machine-readable reason codes; REFUTED reserved for positive
     contradiction (nonexistent target, traced wrong-symbol), never
     for mere absence of observation.
  4. Graph-level precision (over decidable edges), verified share,
     and recall against the traced pair set, with trace coverage of
     the census stated alongside.
  5. Drift check: graph source hashes vs current worktree, reported
     in the audit and at impact-answer time.
  6. Impact queries over the verified subgraph only; the refused
     remainder carries stamps + reason codes (UNVERIFIED_EDGE,
     DRIFTED_FILE, NO_GROUND_TRUTH, NO_SUCH_SYMBOL, AMBIGUOUS_SYMBOL).
  7. Planted-hazard fixtures (registry/dict dispatch, DI container,
     decorator registry, string routing, monkey-patching, name
     shadowing, phantom/stale targets) with known-correct verdicts.
PARTIAL (2):
  8. Ground truth from the repo's own test suite under sys.settrace:
     implemented for unittest-discovery suites. Suites that need a
     third-party runner (e.g. pytest-native) cannot be executed by
     the stdlib-only tracer and report NO_GROUND_TRUTH instead.
  9. Second independent static extraction path: implemented as the
     independent ast census that powers existence refutation. A full
     second call-graph extraction is not in v1.
NOT IN V1 (1):
 10. Ingesting CodeGraph / GitNexus exports (v1 ingests the Graphify
     format and self-built graphs only, per the build scope).
"""


def run_tests() -> bool:
    suite = unittest.TestLoader().discover(
        os.path.join(ROOT, "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return result.wasSuccessful()


def _cli(args, env):
    return subprocess.run(
        [sys.executable, "-m", "edgereckon"] + args,
        capture_output=True, text=True, env=env)


def run_cli_e2e() -> bool:
    env = dict(os.environ, PYTHONPATH=ROOT)
    hazards = os.path.join(ROOT, "fixtures", "hazards_repo")
    ok = True

    def check(cond, label):
        nonlocal ok
        print(f"  [{'ok' if cond else 'FAIL'}] {label}")
        ok = ok and cond

    with tempfile.TemporaryDirectory() as td:
        graph_path = os.path.join(td, "graph.json")
        self_report = os.path.join(td, "self_report.json")
        ext_report = os.path.join(td, "ext_report.json")

        proc = _cli(["build", "--repo", hazards, "--out", graph_path], env)
        check(proc.returncode == 0 and "call edges" in proc.stdout,
              "CLI build")

        proc = _cli(["audit", "--repo", hazards, "--out", self_report], env)
        check(proc.returncode == 0, "CLI audit (self-built graph)")
        with open(self_report) as fh:
            report = json.load(fh)
        s = report["summary"]
        check(s["verified"] >= 6 and s["refuted"] == 0
              and s["unverifiable"] >= 1,
              f"self-graph stamps sane "
              f"(V={s['verified']} R={s['refuted']} U={s['unverifiable']})")
        check(0 < s["recall"] < 1,
              f"self-graph recall strictly between 0 and 1 "
              f"({s['recall']:.3f})")

        proc = _cli(["audit", "--repo", hazards,
                     "--graph", os.path.join(ROOT, "fixtures",
                                             "graphify_hazards.json"),
                     "--out", ext_report], env)
        check(proc.returncode == 0, "CLI audit (Graphify-format graph)")
        with open(ext_report) as fh:
            report = json.load(fh)
        s = report["summary"]
        check((s["verified"], s["refuted"], s["unverifiable"]) == (8, 3, 2),
              f"external-graph stamps exact "
              f"(V={s['verified']} R={s['refuted']} U={s['unverifiable']})")

        proc = _cli(["impact", "--report", self_report,
                     "--symbol", "shop.pricing:compute_tax"], env)
        check(proc.returncode == 0
              and "shop.checkout:total_with_tax" in proc.stdout
              and "REFUSED" in proc.stdout
              and "complete: False" in proc.stdout,
              "CLI impact refuses the unverified remainder")
    return ok


def main() -> int:
    print("== unit tests ==")
    tests_ok = run_tests()
    print("== CLI end-to-end on fixtures ==")
    e2e_ok = run_cli_e2e()
    print(COVERAGE_STATEMENT)
    if tests_ok and e2e_ok:
        print("VALIDATION PASSED")
        return 0
    print("VALIDATION FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
