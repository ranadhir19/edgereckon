"""Tests for edgereckon, run against the planted-hazard fixture.

The fixture's correct verdicts are known in advance (see
fixtures/hazards_repo/README.md), so these tests check the auditor
against ground truth about ground truth -- not against its own
output conventions.
"""

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from edgereckon import audit as audit_mod  # noqa: E402
from edgereckon import graphbuild, impact as impact_mod, ingest  # noqa: E402
from edgereckon import model, tracer  # noqa: E402

FIXTURES = os.path.join(ROOT, "fixtures")
HAZARDS = os.path.join(FIXTURES, "hazards_repo")
GRAPHIFY = os.path.join(FIXTURES, "graphify_hazards.json")


def stamps_by_pair(report):
    return {(e["caller"], e["callee"]): (e["stamp"], e["reason"])
            for e in report["edges"]}


class FixtureAuditBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace, note = tracer.harvest_trace(HAZARDS)
        assert cls.trace is not None, f"trace harvest failed: {note}"
        cls.self_graph = graphbuild.build_graph(HAZARDS)
        cls.self_report = audit_mod.audit(cls.self_graph, HAZARDS, cls.trace)
        data = model.load_graph(GRAPHIFY)
        cls.ext_graph, cls.ext_stats = ingest.ingest(data, repo=HAZARDS)
        cls.ext_report = audit_mod.audit(cls.ext_graph, HAZARDS, cls.trace)


class TestTrace(FixtureAuditBase):
    def test_suite_ran_and_passed(self):
        self.assertEqual(self.trace["tests_run"], 7)
        self.assertTrue(self.trace["ok"])

    def test_known_pairs_traced(self):
        pairs = {tuple(p) for p in self.trace["pairs"]}
        self.assertIn(("shop.checkout:receipt",
                       "shop.checkout:total_with_tax"), pairs)
        self.assertIn(("shop.dispatch:notify",
                       "shop.dispatch:send_email"), pairs)
        # The monkey-patch substitute edge is real and was traced.
        self.assertIn(("shop.checkout:express_total",
                       "tests.test_shop:fake_compute_tax"), pairs)
        # The real compute_tax edge from express_total was NOT traced.
        self.assertNotIn(("shop.checkout:express_total",
                          "shop.pricing:compute_tax"), pairs)


class TestCensusAndBuilder(FixtureAuditBase):
    def test_census(self):
        census = graphbuild.collect_census(HAZARDS)
        self.assertIn("shop.pricing:compute_tax", census)
        self.assertNotIn("shop.pricing:apply_discount", census)
        self.assertNotIn("shop.legacy:charge_card", census)

    def test_builder_edges_and_hashes(self):
        pairs = {(e["caller"], e["callee"]) for e in self.self_graph["edges"]}
        self.assertIn(("shop.checkout:receipt",
                       "shop.checkout:total_with_tax"), pairs)
        # The builder cannot see dynamic dispatch -- by design.
        self.assertNotIn(("shop.dispatch:notify",
                          "shop.dispatch:send_email"), pairs)
        self.assertNotIn(("shop.events:emit",
                          "shop.events:handle_ping"), pairs)
        for relpath in model.iter_python_files(HAZARDS):
            self.assertIn(relpath, self.self_graph["source_hashes"])


class TestSelfGraphStamps(FixtureAuditBase):
    def test_verified_chain(self):
        s = stamps_by_pair(self.self_report)
        for pair in [("shop.checkout:receipt", "shop.checkout:total_with_tax"),
                     ("shop.checkout:total_with_tax", "shop.pricing:compute_tax"),
                     ("shop.checkout:receipt", "shop.pricing:format_price"),
                     ("shop.report:render", "shop.report:format_price"),
                     ("shop.container:build_checkout", "shop.container:Container"),
                     ("shop.container:build_checkout",
                      "shop.container:CheckoutService")]:
            self.assertEqual(s[pair][0], "VERIFIED", pair)

    def test_monkeypatched_edge_never_verified(self):
        s = stamps_by_pair(self.self_report)
        stamp, reason = s[("shop.checkout:express_total",
                           "shop.pricing:compute_tax")]
        self.assertEqual(stamp, "UNVERIFIABLE")
        self.assertEqual(reason, "NOT_OBSERVED")

    def test_self_graph_refutes_nothing_and_misses_dynamic_edges(self):
        summary = self.self_report["summary"]
        self.assertEqual(summary["refuted"], 0)
        self.assertGreater(summary["verified"], 0)
        missed = {tuple(p) for p in summary["missed_traced_pairs"]}
        for pair in [("shop.dispatch:notify", "shop.dispatch:send_email"),
                     ("shop.container:CheckoutService.checkout",
                      "shop.container:TaxService.tax"),
                     ("shop.events:emit", "shop.events:handle_ping"),
                     ("shop.routes:route", "shop.routes:home_page")]:
            self.assertIn(pair, missed)
        self.assertGreater(summary["recall"], 0)
        self.assertLess(summary["recall"], 1)


class TestExternalGraphStamps(FixtureAuditBase):
    def test_counts(self):
        s = self.ext_report["summary"]
        self.assertEqual(s["claimed_edges"], 13)
        self.assertEqual(s["verified"], 8)
        self.assertEqual(s["refuted"], 3)
        self.assertEqual(s["unverifiable"], 2)
        self.assertAlmostEqual(s["precision_decidable"], 8 / 11)

    def test_refutations(self):
        s = stamps_by_pair(self.ext_report)
        self.assertEqual(s[("shop.checkout:total_with_tax",
                            "shop.pricing:apply_discount")],
                         ("REFUTED", "CALLEE_NOT_FOUND"))
        self.assertEqual(s[("shop.checkout:receipt",
                            "shop.legacy:charge_card")],
                         ("REFUTED", "CALLEE_NOT_FOUND"))
        self.assertEqual(s[("shop.report:render",
                            "shop.pricing:format_price")],
                         ("REFUTED", "WRONG_SYMBOL"))

    def test_dynamic_edges_verified_when_claimed(self):
        s = stamps_by_pair(self.ext_report)
        for pair in [("shop.dispatch:notify", "shop.dispatch:send_email"),
                     ("shop.events:emit", "shop.events:handle_ping"),
                     ("shop.routes:route", "shop.routes:home_page"),
                     ("shop.container:CheckoutService.checkout",
                      "shop.container:TaxService.tax"),
                     ("shop.report:render", "shop.report:format_price")]:
            self.assertEqual(s[pair][0], "VERIFIED", pair)

    def test_unexecuted_registry_value_unverifiable(self):
        s = stamps_by_pair(self.ext_report)
        self.assertEqual(s[("shop.dispatch:notify",
                            "shop.dispatch:send_sms")],
                         ("UNVERIFIABLE", "CALLEE_NOT_EXECUTED"))

    def test_ingest_skips_non_call_edges(self):
        self.assertEqual(self.ext_stats["non_call_edges"], 1)


class TestNoTrace(FixtureAuditBase):
    def test_no_trace_stamps(self):
        report = audit_mod.audit(self.ext_graph, HAZARDS, None)
        s = stamps_by_pair(report)
        # Existence refutation does not need a trace.
        self.assertEqual(s[("shop.checkout:total_with_tax",
                            "shop.pricing:apply_discount")][0], "REFUTED")
        # Everything else is honestly unverifiable.
        self.assertEqual(s[("shop.checkout:express_total",
                            "shop.pricing:compute_tax")],
                         ("UNVERIFIABLE", "NO_GROUND_TRUTH"))
        self.assertEqual(report["summary"]["verified"], 0)

    def test_impact_refuses_without_ground_truth(self):
        report = audit_mod.audit(self.self_graph, HAZARDS, None)
        result = impact_mod.impact(report, "shop.pricing:compute_tax")
        self.assertFalse(result["answered"])
        self.assertEqual(result["reason"], "NO_GROUND_TRUTH")


class TestImpact(FixtureAuditBase):
    def test_verified_radius_and_refused_remainder(self):
        result = impact_mod.impact(self.self_report,
                                   "shop.pricing:compute_tax")
        self.assertTrue(result["answered"])
        radius = {i["symbol"] for i in result["verified_blast_radius"]}
        self.assertIn("shop.checkout:total_with_tax", radius)
        self.assertIn("shop.checkout:receipt", radius)
        refused = {(r["caller"], r["callee"])
                   for r in result["refused_remainder"]}
        self.assertIn(("shop.checkout:express_total",
                       "shop.pricing:compute_tax"), refused)
        self.assertFalse(result["complete"])
        self.assertIn("UNVERIFIED_EDGE", result["incompleteness_reasons"])

    def test_unknown_and_suffix_symbols(self):
        result = impact_mod.impact(self.self_report, "shop.nope:nothing")
        self.assertFalse(result["answered"])
        self.assertEqual(result["reason"], "NO_SUCH_SYMBOL")
        by_suffix = impact_mod.impact(self.self_report, "compute_tax")
        self.assertTrue(by_suffix["answered"])
        self.assertEqual(by_suffix["symbol"], "shop.pricing:compute_tax")


class TestDrift(unittest.TestCase):
    def test_drift_detected_and_marks_impact(self):
        with tempfile.TemporaryDirectory() as td:
            work = os.path.join(td, "repo")
            shutil.copytree(HAZARDS, work,
                            ignore=shutil.ignore_patterns("__pycache__"))
            graph = graphbuild.build_graph(work)
            clean = audit_mod.audit(graph, work, None)
            self.assertEqual(clean["drift"]["status"], "CLEAN")
            pricing = os.path.join(work, "shop", "pricing.py")
            with open(pricing, "a", encoding="utf-8") as fh:
                fh.write("\n# drift: comment added after graph build\n")
            trace, note = tracer.harvest_trace(work)
            self.assertIsNotNone(trace, note)
            report = audit_mod.audit(graph, work, trace)
            self.assertEqual(report["drift"]["status"], "DRIFTED")
            drifted = {d["file"] for d in report["drift"]["drifted_files"]}
            self.assertIn("shop/pricing.py", drifted)
            result = impact_mod.impact(report, "shop.pricing:compute_tax")
            self.assertTrue(result["answered"])
            self.assertIn("shop/pricing.py",
                          result["drift"]["drifted_files_in_neighborhood"])
            self.assertFalse(result["complete"])
            self.assertIn("DRIFTED_FILE", result["incompleteness_reasons"])


if __name__ == "__main__":
    unittest.main()
