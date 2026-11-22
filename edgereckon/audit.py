"""The audit: stamp every claimed call edge against ground truth.

Stamps and reason codes
-----------------------
VERIFIED / OBSERVED
    The caller->callee pair was actually executed under the traced
    test run. (A traced call to ``SomeClass.__init__`` also verifies a
    claimed edge to the class node ``SomeClass`` -- instantiation is
    that call.)

REFUTED / TARGET_NOT_FOUND
    The claimed callee (or caller) is asserted to live in this repo
    but no such symbol is defined in the current worktree, per an
    independent ``ast`` census. Existence is checkable without a
    trace, so this refutation does not depend on test coverage.
REFUTED / WRONG_SYMBOL
    The claimed callee exists, but the caller's own module defines a
    symbol with the same final name, the trace shows the caller
    invoking *that* local symbol, and the claimed edge was never
    observed -- positive traced evidence the name at the call site
    binds to a different symbol than the graph asserts.

UNVERIFIABLE -- absence of observation is never refutation:
    NO_GROUND_TRUTH     the repo's tests could not be run / ran none
    TARGET_OUTSIDE_REPO the claimed target is not asserted to be in
                        this repo at all (e.g. a third-party symbol)
    CALLER_NOT_EXECUTED the caller never ran under the traced tests
    CALLEE_NOT_EXECUTED the callee never ran under the traced tests
    NOT_OBSERVED        both ran, the pair was not observed (untested
                        path, dynamic dispatch, monkey-patched binding,
                        ... -- the trace cannot distinguish these)

Metrics
-------
precision_decidable = VERIFIED / (VERIFIED + REFUTED) -- precision
    over the edges the evidence could actually decide.
verified_share      = VERIFIED / all claimed edges.
recall              = traced pairs (both endpoints defined in the
    worktree) that the graph claims, over all such traced pairs.
    Traces prove presence only, so recall is measured against what
    the tests actually executed -- the report states test coverage of
    the census alongside it, and a low recall against a thin test
    suite says as much about the suite as about the graph.
"""

import os

from . import graphbuild, model

VERIFIED = "VERIFIED"
REFUTED = "REFUTED"
UNVERIFIABLE = "UNVERIFIABLE"


def _repo_internal(sid: str, census: dict, graph_nodes: dict) -> bool:
    """Is this symbol asserted to live inside the audited repo?"""
    if sid in census:
        return True
    node = graph_nodes.get(sid)
    if node and node.get("file"):
        return True
    module, _ = model.split_symbol_id(sid)
    top = module.split(".")[0]
    census_tops = {model.split_symbol_id(s)[0].split(".")[0] for s in census}
    return top in census_tops


def _normalise_pairs(trace: dict, census: dict):
    """Traced pairs with ``K.__init__`` collapsed to the class node K
    when K is a defined class -- instantiation is a call to K."""
    pairs = set()
    for caller, callee in trace.get("pairs", []):
        if callee.endswith(".__init__"):
            klass = callee[:-len(".__init__")]
            if klass in census and census[klass]["kind"] == "class":
                callee = klass
        pairs.add((caller, callee))
    return pairs


def drift_check(graph: dict, repo: str) -> dict:
    """Compare the graph's recorded source hashes with the worktree."""
    hashes = graph.get("source_hashes") or {}
    if not hashes:
        return {"status": "UNKNOWN", "reason": "NO_PROVENANCE",
                "drifted_files": [], "added_files": []}
    drifted = []
    for relpath, recorded in sorted(hashes.items()):
        current_path = os.path.join(repo, relpath)
        if not os.path.exists(current_path):
            drifted.append({"file": relpath, "change": "deleted"})
        elif model.sha256_file(current_path) != recorded:
            drifted.append({"file": relpath, "change": "modified"})
    current_files = set(model.iter_python_files(repo))
    added = sorted(f for f in current_files if f not in hashes)
    return {"status": "DRIFTED" if drifted else "CLEAN",
            "reason": None,
            "drifted_files": drifted, "added_files": added}


def audit(graph: dict, repo: str, trace) -> dict:
    """Produce the full audit report for a normalised graph."""
    repo = os.path.abspath(repo)
    census = graphbuild.collect_census(repo)
    graph_nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])

    if trace is not None:
        pairs = _normalise_pairs(trace, census)
        executed = set(trace.get("executed", []))
        # Executed set also collapses __init__ to its class.
        executed = {p[:-len(".__init__")] if p.endswith(".__init__")
                    and p[:-len(".__init__")] in census else p
                    for p in executed}
        callers_seen = {c for c, _ in pairs}
    else:
        pairs, executed, callers_seen = set(), set(), set()

    # Per-caller traced callees, for WRONG_SYMBOL evidence + detail.
    traced_callees = {}
    for caller, callee in pairs:
        traced_callees.setdefault(caller, set()).add(callee)

    stamped = []
    counts = {VERIFIED: 0, REFUTED: 0, UNVERIFIABLE: 0}
    for edge in edges:
        caller, callee = edge["caller"], edge["callee"]
        stamp, reason, detail = _stamp_edge(
            caller, callee, census, graph_nodes, trace, pairs, executed,
            callers_seen, traced_callees)
        counts[stamp] += 1
        stamped.append({
            "caller": caller, "callee": callee, "stamp": stamp,
            "reason": reason, "detail": detail,
            "provenance": edge.get("provenance", ""),
            "file": edge.get("file", ""), "line": edge.get("line", 0),
        })

    claimed_pairs = {(e["caller"], e["callee"]) for e in edges}
    relevant_pairs = {(c, k) for (c, k) in pairs
                      if c in census and k in census}
    hit_pairs = relevant_pairs & claimed_pairs
    missed = sorted(relevant_pairs - claimed_pairs)
    decided = counts[VERIFIED] + counts[REFUTED]
    metrics = {
        "claimed_edges": len(edges),
        "verified": counts[VERIFIED],
        "refuted": counts[REFUTED],
        "unverifiable": counts[UNVERIFIABLE],
        "precision_decidable": (counts[VERIFIED] / decided) if decided else None,
        "verified_share": (counts[VERIFIED] / len(edges)) if edges else None,
        "traced_relevant_pairs": len(relevant_pairs),
        "traced_pairs_claimed": len(hit_pairs),
        "recall": (len(hit_pairs) / len(relevant_pairs))
                  if relevant_pairs else None,
        "missed_traced_pairs": [list(p) for p in missed],
        "census_symbols": len(census),
        "executed_census_symbols": len(executed & set(census)),
    }

    if trace is None:
        ground_truth = {"status": "NO_GROUND_TRUTH", "tests_run": 0,
                        "tests_ok": False, "traced_pairs": 0}
    else:
        ground_truth = {
            "status": "OK", "tests_run": trace.get("tests_run", 0),
            "tests_ok": trace.get("ok", False),
            "failures": trace.get("failures", 0),
            "errors": trace.get("errors", 0),
            "traced_pairs": len(pairs),
        }

    return {
        "tool": "edgereckon",
        "version": __import__("edgereckon").__version__,
        "repo": repo,
        "graph_tool": graph.get("tool", ""),
        "ground_truth": ground_truth,
        "ground_truth_note": (
            "Traces prove presence: an observed pair is a real call. "
            "Absence of a pair is not proof of absence -- it may be an "
            "untested path. REFUTED is reserved for edges the evidence "
            "positively contradicts (nonexistent target, or traced "
            "wrong-symbol resolution)."),
        "nodes": [{"id": n["id"], "file": n.get("file", ""),
                   "kind": n.get("kind", "")}
                  for n in graph.get("nodes", [])],
        "edges": stamped,
        "summary": metrics,
        "drift": drift_check(graph, repo),
    }


def _stamp_edge(caller, callee, census, graph_nodes, trace, pairs,
                executed, callers_seen, traced_callees):
    # 1. Observed at runtime -- the strongest stamp, checked first so
    #    no refutation rule can override a call that demonstrably ran.
    if trace is not None and (caller, callee) in pairs:
        return VERIFIED, "OBSERVED", "pair executed under the traced test run"

    # 2. Existence refutation (trace-independent): the graph asserts a
    #    repo-internal symbol the worktree does not define.
    for role, sid in (("callee", callee), ("caller", caller)):
        if sid not in census and _repo_internal(sid, census, graph_nodes):
            node = graph_nodes.get(sid) or {}
            where = node.get("file") or model.split_symbol_id(sid)[0]
            return REFUTED, f"{role.upper()}_NOT_FOUND", \
                f"claimed {role} {sid} is not defined in the worktree " \
                f"(asserted location: {where})"

    # 3. Targets not asserted to be in this repo cannot be judged here.
    if callee not in census:
        return UNVERIFIABLE, "TARGET_OUTSIDE_REPO", \
            "claimed callee is not a symbol of this repo"

    # 4. No trace -> nothing more can be decided.
    if trace is None:
        return UNVERIFIABLE, "NO_GROUND_TRUTH", \
            "the repo's test suite produced no usable trace"

    # 5. Wrong-symbol refutation: the caller's module defines the same
    #    final name, the trace shows the caller invoking the local
    #    symbol, and the claimed edge never fired.
    caller_module, _ = model.split_symbol_id(caller)
    _, callee_qual = model.split_symbol_id(callee)
    callee_name = callee_qual.split(".")[-1]
    local_sid = model.symbol_id(caller_module, callee_name)
    if local_sid != callee and local_sid in census \
            and local_sid in traced_callees.get(caller, set()):
        return REFUTED, "WRONG_SYMBOL", \
            f"caller invokes the local symbol {local_sid} of the same " \
            f"name; the claimed target {callee} was never observed " \
            f"from this caller"

    # 6. Unobserved and not refutable: say which evidence is missing.
    if caller not in callers_seen:
        return UNVERIFIABLE, "CALLER_NOT_EXECUTED", \
            "caller never executed under the traced tests"
    if callee not in executed:
        return UNVERIFIABLE, "CALLEE_NOT_EXECUTED", \
            "callee never executed under the traced tests"
    observed = sorted(traced_callees.get(caller, set()))
    detail = "both endpoints executed; this pair was not observed"
    if observed:
        detail += f"; caller was observed calling: {', '.join(observed)}"
    return UNVERIFIABLE, "NOT_OBSERVED", detail
