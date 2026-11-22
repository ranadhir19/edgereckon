"""Static extraction with the stdlib ``ast`` module.

Two products share one walk of the worktree:

- the **census**: every function / method / class actually defined in
  the repo right now. The auditor uses it as an independent extraction
  path -- a claimed edge whose target is absent from the census is
  refutable on existence grounds alone, no trace needed.
- the **self-built graph**: a deliberately simple static call graph
  (module-level functions, classes and methods as nodes; call edges
  where the target resolves by bare name, ``from``-import, module
  attribute, or ``self.``). edgereckon audits graphs; it does not try
  to out-build the graph builders. Anything dynamic -- registry or
  dict dispatch, DI containers, decorator registries, string routing,
  monkey-patching -- is exactly what this builder cannot see, which is
  the point: the audit measures the consequences.
"""

import ast
import os

from . import model

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


def _collect_defs(tree: ast.Module, module: str, relpath: str):
    """All definitions in one module: {qualname: node-dict}."""
    nodes = {}

    def walk(body, prefix):
        for stmt in body:
            if isinstance(stmt, _FUNC):
                qual = f"{prefix}{stmt.name}"
                nodes[qual] = {"qualname": qual, "kind": "function",
                               "line": stmt.lineno, "node": stmt}
                walk(stmt.body, f"{qual}.")
            elif isinstance(stmt, ast.ClassDef):
                qual = f"{prefix}{stmt.name}"
                nodes[qual] = {"qualname": qual, "kind": "class",
                               "line": stmt.lineno, "node": stmt}
                for sub in stmt.body:
                    if isinstance(sub, _FUNC):
                        mqual = f"{qual}.{sub.name}"
                        nodes[mqual] = {"qualname": mqual, "kind": "method",
                                        "line": sub.lineno, "node": sub}
                        walk(sub.body, f"{mqual}.")
                    elif isinstance(sub, ast.ClassDef):
                        walk([sub], f"{qual}.")

    walk(tree.body, "")
    return nodes


def _parse_file(repo: str, relpath: str):
    path = os.path.join(repo, relpath)
    try:
        with open(path, encoding="utf-8") as fh:
            return ast.parse(fh.read(), filename=relpath)
    except (SyntaxError, UnicodeDecodeError):
        return None


def collect_census(repo: str) -> dict:
    """{symbol_id: {"file": relpath, "line": int, "kind": str}} for the
    whole worktree, extracted fresh from the current files."""
    census = {}
    for relpath in model.iter_python_files(repo):
        tree = _parse_file(repo, relpath)
        if tree is None:
            continue
        module = model.module_name_for(relpath)
        for qual, info in _collect_defs(tree, module, relpath).items():
            census[model.symbol_id(module, qual)] = {
                "file": relpath, "line": info["line"], "kind": info["kind"]}
    return census


def _imports(tree: ast.Module, module: str):
    """(from_imports, module_aliases) for one module.

    from_imports: local name -> (source module, original name)
    module_aliases: local name -> dotted module
    """
    from_imports = {}
    module_aliases = {}
    package_parts = module.split(".")[:-1] if "." in module else []
    # For a package __init__ module, the module IS the package.
    for stmt in ast.walk(tree):
        if isinstance(stmt, ast.ImportFrom):
            base = stmt.module or ""
            if stmt.level:
                keep = len(package_parts) - (stmt.level - 1)
                parts = package_parts[:keep] if keep > 0 else []
                if base:
                    parts = parts + base.split(".")
                base = ".".join(parts)
            for alias in stmt.names:
                if alias.name == "*":
                    continue
                from_imports[alias.asname or alias.name] = (base, alias.name)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.asname:
                    module_aliases[alias.asname] = alias.name
                else:
                    module_aliases[alias.name.split(".")[0]] = \
                        alias.name.split(".")[0]
    return from_imports, module_aliases


def _calls_in(func_node):
    """Call nodes in a function body, pruning nested def/class bodies
    (their calls belong to the nested symbol's frame at runtime)."""
    found = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node):
            found.append(node)
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            pass

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            pass

        def visit_Lambda(self, node):
            pass

    for stmt in func_node.body:
        Visitor().visit(stmt)
    return found


def build_graph(repo: str) -> dict:
    """Build the self-built static call graph for a Python repo."""
    repo = os.path.abspath(repo)
    files = model.iter_python_files(repo)
    trees = {}
    all_defs = {}  # module -> {qualname: info}
    for relpath in files:
        tree = _parse_file(repo, relpath)
        if tree is None:
            continue
        trees[relpath] = tree
        module = model.module_name_for(relpath)
        all_defs[module] = _collect_defs(tree, module, relpath)

    def node_exists(sid):
        module, qual = model.split_symbol_id(sid)
        return module in all_defs and qual in all_defs[module]

    nodes = []
    for relpath in files:
        module = model.module_name_for(relpath)
        for qual, info in sorted(all_defs.get(module, {}).items()):
            nodes.append({
                "id": model.symbol_id(module, qual),
                "kind": info["kind"],
                "file": relpath,
                "line": info["line"],
                "name": qual,
            })

    edges = []
    seen = set()
    for relpath in files:
        module = model.module_name_for(relpath)
        tree = trees[relpath]
        defs = all_defs[module]
        from_imports, module_aliases = _imports(tree, module)
        for qual, info in defs.items():
            if info["kind"] == "class":
                continue
            caller = model.symbol_id(module, qual)
            # Names defined directly inside this function (nested defs).
            nested = {}
            for sub in info["node"].body:
                if isinstance(sub, _FUNC):
                    nested[sub.name] = f"{qual}.{sub.name}"
            class_prefix = qual.rsplit(".", 1)[0] if info["kind"] == "method" \
                else None
            for call in _calls_in(info["node"]):
                target = _resolve(call.func, module, defs, from_imports,
                                  module_aliases, nested, class_prefix,
                                  node_exists)
                if target is None:
                    continue
                key = (caller, target)
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    "caller": caller, "callee": target, "kind": "call",
                    "file": relpath, "line": call.lineno,
                    "provenance": "EXTRACTED",
                })

    source_hashes = {
        relpath: model.sha256_file(os.path.join(repo, relpath))
        for relpath in files
    }
    return {
        "format": model.GRAPH_FORMAT,
        "tool": "edgereckon-static",
        "repo": repo,
        "nodes": nodes,
        "edges": edges,
        "source_hashes": source_hashes,
    }


def _resolve(func, module, defs, from_imports, module_aliases, nested,
             class_prefix, node_exists):
    """Resolve a call target expression to a symbol id, or None.

    Deliberately simple: bare names (local defs, nested defs,
    from-imports), module attributes via import aliases, and
    ``self.method()`` within the same class. Everything else --
    variables, subscripts, attribute chains, getattr -- is unresolvable
    here by design.
    """
    if isinstance(func, ast.Name):
        name = func.id
        if name in nested:
            return model.symbol_id(module, nested[name])
        if name in defs:
            return model.symbol_id(module, name)
        if name in from_imports:
            src_module, orig = from_imports[name]
            sid = model.symbol_id(src_module, orig)
            return sid if node_exists(sid) else None
        return None
    if isinstance(func, ast.Attribute):
        # self.method()
        if isinstance(func.value, ast.Name) and func.value.id == "self" \
                and class_prefix:
            sid = model.symbol_id(module, f"{class_prefix}.{func.attr}")
            return sid if node_exists(sid) else None
        # alias.attr where alias is an imported module
        if isinstance(func.value, ast.Name) and func.value.id in module_aliases:
            src_module = module_aliases[func.value.id]
            sid = model.symbol_id(src_module, func.attr)
            return sid if node_exists(sid) else None
        return None
    return None
