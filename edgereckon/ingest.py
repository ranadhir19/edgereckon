"""Ingest an external graph into the internal edge format.

v1 supports the Graphify-format ``graph.json``: a node-link JSON
object with ``nodes`` and ``links`` (some exports use ``edges``).
The ingester is deliberately tolerant about field spellings, because
exports vary:

- node id: ``"path/to/file.py::Qual.name"``, or a plain id together
  with ``source_file``/``file`` and ``label``/``qualname``/``name``;
- edge endpoints: ``source``/``target`` (node-link) or
  ``caller``/``callee``;
- edge relation: ``relation``/``type``/``kind``; only call relations
  (``calls``/``call``) are audited -- other relations are counted in
  the returned stats and dropped.

Node ids are canonicalised to ``<dotted.module>:<qualname>`` so they
can be compared against trace ground truth and the worktree census.
A node whose file cannot be determined keeps its raw id; edges that
touch it will be stamped on outside-repo grounds, never silently
passed. Ingesting a graph file is data processing only -- no code of
any graph tool is used or needed here.
"""

import os

from . import model

_CALL_RELATIONS = {"calls", "call", "CALLS", "CALL"}


def _node_canonical(node):
    """Canonical symbol id + file for one external node, best effort."""
    raw_id = str(node.get("id", ""))
    src = node.get("source_file") or node.get("file") or ""
    label = node.get("qualname") or node.get("label") or node.get("name") or ""
    if "::" in raw_id:
        left, _, right = raw_id.partition("::")
        if left.endswith(".py"):
            return model.symbol_id(model.module_name_for(left), right), left
        if ":" in raw_id and not src:
            return raw_id, src
    if src:
        module = model.module_name_for(src) if src.endswith(".py") else src
        qual = label or raw_id.rsplit(":", 1)[-1]
        return model.symbol_id(module, qual), src
    return raw_id, src


def ingest(data: dict, repo: str = "") -> (dict, dict):
    """Normalise an external graph dict. Returns (graph, stats)."""
    raw_nodes = data.get("nodes") or []
    raw_edges = data.get("links") or data.get("edges") or []
    id_map = {}
    nodes = []
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        canon, src = _node_canonical(node)
        id_map[str(node.get("id", ""))] = canon
        line = node.get("source_location") or node.get("line") or 0
        try:
            line = int(str(line).split(":")[-1].lstrip("L"))
        except (ValueError, TypeError):
            line = 0
        nodes.append({
            "id": canon,
            "kind": str(node.get("type") or node.get("kind") or "function"),
            "file": src,
            "line": line,
            "name": model.split_symbol_id(canon)[1] if ":" in canon else canon,
        })

    edges = []
    stats = {"nodes_in": len(raw_nodes), "edges_in": len(raw_edges),
             "non_call_edges": 0, "dangling_edges": 0}
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        relation = edge.get("relation") or edge.get("type") \
            or edge.get("kind") or "calls"
        if relation not in _CALL_RELATIONS:
            stats["non_call_edges"] += 1
            continue
        src_raw = str(edge.get("source") or edge.get("caller") or "")
        tgt_raw = str(edge.get("target") or edge.get("callee") or "")
        caller = id_map.get(src_raw, src_raw)
        callee = id_map.get(tgt_raw, tgt_raw)
        if src_raw not in id_map or tgt_raw not in id_map:
            stats["dangling_edges"] += 1
        edges.append({
            "caller": caller, "callee": callee, "kind": "call",
            "file": edge.get("source_file") or "",
            "line": 0,
            "provenance": str(edge.get("confidence")
                              or edge.get("provenance") or ""),
        })

    graph = {
        "format": model.GRAPH_FORMAT,
        "tool": str(data.get("tool") or data.get("generator")
                    or "external-graph"),
        "repo": repo or str(data.get("repo") or ""),
        "nodes": nodes,
        "edges": edges,
        # External exports carry no per-file build hashes that v1 can
        # trust, so drift for ingested graphs is reported UNKNOWN /
        # NO_PROVENANCE unless the export happens to include them.
        "source_hashes": data.get("source_hashes") or {},
    }
    return graph, stats
