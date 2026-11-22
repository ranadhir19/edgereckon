"""Command-line interface.

    edgereckon build  --repo PATH [--out graph.json]
    edgereckon audit  --repo PATH [--graph graph.json] [--test-dir tests]
                      [--no-trace] [--trace-file trace.json] [--out report.json]
    edgereckon impact --report report.json --symbol MODULE:QUALNAME

Without ``--graph``, ``audit`` builds the self-built static graph for
the repo and audits that. With ``--graph`` pointing at a Graphify
``graph.json`` (or an internal-format graph), it audits that graph.
"""

import argparse
import json
import sys

from . import audit as audit_mod
from . import graphbuild, impact as impact_mod, ingest, model, tracer


def _fmt_metric(value):
    return "n/a" if value is None else f"{value:.3f}"


def print_audit_summary(report: dict) -> None:
    s = report["summary"]
    gt = report["ground_truth"]
    print(f"repo: {report['repo']}")
    print(f"graph: {report['graph_tool'] or 'unknown'}")
    if gt["status"] == "OK":
        print(f"ground truth: {gt['tests_run']} tests "
              f"({'passed' if gt['tests_ok'] else 'FAILURES PRESENT'}), "
              f"{gt['traced_pairs']} traced call pairs")
    else:
        print("ground truth: NONE -- edges can only be refuted on "
              "existence grounds or left UNVERIFIABLE")
    print(f"claimed call edges: {s['claimed_edges']}")
    print(f"  VERIFIED:     {s['verified']}")
    print(f"  REFUTED:      {s['refuted']}")
    print(f"  UNVERIFIABLE: {s['unverifiable']}")
    print(f"precision (decidable edges): {_fmt_metric(s['precision_decidable'])}")
    print(f"verified share of claimed:   {_fmt_metric(s['verified_share'])}")
    print(f"recall vs traced pairs:      {_fmt_metric(s['recall'])} "
          f"({s['traced_pairs_claimed']}/{s['traced_relevant_pairs']})")
    print(f"trace coverage: {s['executed_census_symbols']}/"
          f"{s['census_symbols']} defined symbols executed")
    drift = report["drift"]
    if drift["status"] == "DRIFTED":
        files = ", ".join(d["file"] for d in drift["drifted_files"])
        print(f"drift: DRIFTED -- {files}")
    elif drift["status"] == "UNKNOWN":
        print("drift: UNKNOWN (graph carries no source hashes)")
    else:
        print("drift: clean")
    for e in report["edges"]:
        if e["stamp"] != audit_mod.VERIFIED:
            print(f"  [{e['stamp']}/{e['reason']}] "
                  f"{e['caller']} -> {e['callee']}")


def print_impact_summary(result: dict) -> None:
    if not result.get("answered"):
        print(f"REFUSED: {result['reason']} (symbol: {result['symbol']})")
        if result.get("candidates"):
            print("  candidates: " + ", ".join(result["candidates"]))
        if result.get("detail"):
            print(f"  {result['detail']}")
        return
    print(f"impact of changing {result['symbol']}:")
    if result["verified_blast_radius"]:
        for item in result["verified_blast_radius"]:
            print(f"  depth {item['depth']}: {item['symbol']} (verified)")
    else:
        print("  no verified callers")
    for r in result["refused_remainder"]:
        print(f"  REFUSED [{r['stamp']}/{r['reason']}] "
              f"{r['caller']} -> {r['callee']}")
    drift = result["drift"]
    if drift["drifted_files_in_neighborhood"]:
        print("  DRIFTED neighborhood files: "
              + ", ".join(drift["drifted_files_in_neighborhood"]))
    print(f"complete: {result['complete']}"
          + ("" if result["complete"] else
             f" -- incomplete: {', '.join(result['incompleteness_reasons'])}"))


def _load_or_build_graph(args) -> dict:
    if args.graph:
        data = model.load_graph(args.graph)
        if model.is_internal_graph(data):
            return data
        graph, stats = ingest.ingest(data, repo=args.repo)
        print(f"ingested external graph: {stats['nodes_in']} nodes, "
              f"{stats['edges_in']} edges "
              f"({stats['non_call_edges']} non-call edges skipped, "
              f"{stats['dangling_edges']} dangling endpoints)",
              file=sys.stderr)
        return graph
    return graphbuild.build_graph(args.repo)


def cmd_build(args) -> int:
    graph = graphbuild.build_graph(args.repo)
    if args.out:
        model.save_json(graph, args.out)
    print(f"built graph: {len(graph['nodes'])} nodes, "
          f"{len(graph['edges'])} call edges")
    return 0


def cmd_audit(args) -> int:
    graph = _load_or_build_graph(args)
    trace = None
    if args.trace_file:
        with open(args.trace_file, encoding="utf-8") as fh:
            trace = json.load(fh)
        if trace.get("load_error") or trace.get("tests_run", 0) == 0:
            print(f"warning: trace file carries no ground truth: "
                  f"{trace.get('load_error', 'zero tests')}",
                  file=sys.stderr)
            trace = None
    elif not args.no_trace:
        trace, note = tracer.harvest_trace(args.repo, args.test_dir)
        if trace is None:
            print(f"warning: {note}", file=sys.stderr)
    report = audit_mod.audit(graph, args.repo, trace)
    if args.out:
        model.save_json(report, args.out)
    print_audit_summary(report)
    return 0


def cmd_impact(args) -> int:
    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)
    result = impact_mod.impact(report, args.symbol)
    if args.out:
        model.save_json(result, args.out)
    print_impact_summary(result)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="edgereckon",
        description="Audit a code knowledge graph's call edges against "
                    "execution traces from the repo's own test suite.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="build the self-built static "
                                           "graph for a Python repo")
    p_build.add_argument("--repo", required=True)
    p_build.add_argument("--out")
    p_build.set_defaults(fn=cmd_build)

    p_audit = sub.add_parser("audit", help="audit a graph against trace "
                                           "ground truth")
    p_audit.add_argument("--repo", required=True)
    p_audit.add_argument("--graph",
                         help="Graphify graph.json or internal graph; "
                              "default: build the static graph")
    p_audit.add_argument("--test-dir", default="tests")
    p_audit.add_argument("--no-trace", action="store_true",
                         help="skip ground-truth harvesting")
    p_audit.add_argument("--trace-file",
                         help="use a pre-harvested trace JSON")
    p_audit.add_argument("--out")
    p_audit.set_defaults(fn=cmd_audit)

    p_impact = sub.add_parser("impact", help="impact query over the "
                                             "verified subgraph of an "
                                             "audit report")
    p_impact.add_argument("--report", required=True)
    p_impact.add_argument("--symbol", required=True)
    p_impact.add_argument("--out")
    p_impact.set_defaults(fn=cmd_impact)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
