"""Impact queries over the verified subgraph only.

``impact(report, symbol)`` answers "what breaks if I change X?" as:
the blast radius reachable through VERIFIED edges alone (reverse
reachability -- who calls X, who calls them, ...), plus the refused
remainder: every claimed incoming edge that could not be verified,
returned with its stamp and reason code, and a drift flag when the
answer's neighborhood touches files that changed since the graph was
built. An answer is ``complete`` only when the refused remainder is
empty and no neighborhood file drifted. Where the symbol is unknown
or no ground truth exists at all, the query refuses outright with a
machine-readable reason instead of guessing.
"""

from . import audit as audit_mod


def impact(report: dict, symbol: str) -> dict:
    edges = report.get("edges", [])
    node_files = {n["id"]: n.get("file", "")
                  for n in report.get("nodes", [])}
    known = set(node_files) | {e["caller"] for e in edges} \
        | {e["callee"] for e in edges}

    if symbol not in known:
        # Allow an unambiguous suffix match ("compute_tax" ->
        # "shop.pricing:compute_tax"); ambiguity is a refusal too.
        matches = sorted(s for s in known
                         if s == symbol or s.endswith(":" + symbol)
                         or s.endswith("." + symbol))
        if len(matches) == 1:
            symbol = matches[0]
        elif len(matches) > 1:
            return {"answered": False, "symbol": symbol,
                    "reason": "AMBIGUOUS_SYMBOL",
                    "candidates": matches}
        else:
            return {"answered": False, "symbol": symbol,
                    "reason": "NO_SUCH_SYMBOL"}

    if report.get("ground_truth", {}).get("status") != "OK":
        return {"answered": False, "symbol": symbol,
                "reason": "NO_GROUND_TRUTH",
                "detail": "the audit behind this report obtained no "
                          "execution trace, so no edge is verified and "
                          "no impact answer can be given"}

    verified_in = {}
    unverified_in = {}
    for e in edges:
        bucket = verified_in if e["stamp"] == audit_mod.VERIFIED \
            else unverified_in
        bucket.setdefault(e["callee"], []).append(e)

    # Reverse BFS over verified edges only.
    radius = {symbol: 0}
    frontier = [symbol]
    while frontier:
        nxt = []
        for node in frontier:
            for e in verified_in.get(node, []):
                if e["caller"] not in radius:
                    radius[e["caller"]] = radius[node] + 1
                    nxt.append(e["caller"])
        frontier = nxt

    refused = []
    for node in radius:
        for e in unverified_in.get(node, []):
            refused.append({
                "caller": e["caller"], "callee": e["callee"],
                "stamp": e["stamp"], "reason": e["reason"],
                "detail": e["detail"],
            })
    refused.sort(key=lambda r: (r["callee"], r["caller"]))

    drifted_files = {d["file"] for d in
                     report.get("drift", {}).get("drifted_files", [])}
    neighborhood_files = {node_files.get(n, "") for n in radius}
    drift_hits = sorted(f for f in neighborhood_files if f in drifted_files)
    reasons = []
    if refused:
        reasons.append("UNVERIFIED_EDGE")
    if drift_hits:
        reasons.append("DRIFTED_FILE")

    return {
        "answered": True,
        "symbol": symbol,
        "verified_blast_radius": [
            {"symbol": s, "depth": d}
            for s, d in sorted(radius.items(), key=lambda kv: (kv[1], kv[0]))
            if s != symbol
        ],
        "refused_remainder": refused,
        "drift": {
            "status": report.get("drift", {}).get("status", "UNKNOWN"),
            "drifted_files_in_neighborhood": drift_hits,
        },
        "complete": not refused and not drift_hits,
        "incompleteness_reasons": reasons,
    }
