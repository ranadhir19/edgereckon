"""Shared model: canonical symbol ids and the internal graph format.

A symbol id is ``<dotted.module>:<qualname>`` -- for example
``shop.pricing:compute_tax`` or ``shop.container:CheckoutService.checkout``.
The module part is derived from the file's path relative to the repo
root (``shop/pricing.py`` -> ``shop.pricing``; ``shop/__init__.py`` ->
``shop``; ``mod.py`` -> ``mod``).

The internal graph format (``edgereckon-graph/1``) is a JSON object:

    {
      "format": "edgereckon-graph/1",
      "tool": "<who produced this graph>",
      "repo": "<absolute repo path at build time>",
      "nodes": [{"id": ..., "kind": "function|method|class",
                 "file": "<repo-relative path>", "line": int,
                 "name": "<qualname>"}],
      "edges": [{"caller": id, "callee": id, "kind": "call",
                 "file": ..., "line": int, "provenance": str}],
      "source_hashes": {"<repo-relative path>": "sha256:<hex>"}
    }

Only call edges are audited; other relations an ingested graph may
carry (contains, imports, ...) are counted and reported, never stamped.
"""

import hashlib
import json
import os

GRAPH_FORMAT = "edgereckon-graph/1"


def module_name_for(relpath: str) -> str:
    """Dotted module name for a repo-relative ``.py`` path."""
    parts = relpath.replace(os.sep, "/").split("/")
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def symbol_id(module: str, qualname: str) -> str:
    return f"{module}:{qualname}"


def split_symbol_id(sid: str):
    """Split ``module:qualname`` into (module, qualname)."""
    module, _, qualname = sid.partition(":")
    return module, qualname


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def iter_python_files(repo: str):
    """All ``.py`` files under repo, repo-relative, sorted.

    Hidden directories, ``__pycache__`` and ``.git`` are skipped.
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(
            d for d in dirnames
            if d != "__pycache__" and d != ".git" and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), repo))
    return sorted(out)


def load_graph(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: graph JSON must be an object")
    return data


def is_internal_graph(data: dict) -> bool:
    if data.get("format") == GRAPH_FORMAT:
        return True
    edges = data.get("edges") or []
    return bool(edges) and isinstance(edges[0], dict) and "caller" in edges[0]


def save_json(data, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
