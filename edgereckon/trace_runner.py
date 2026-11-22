"""Trace runner: executed as a subprocess inside the target repo.

Usage:
    python -m edgereckon.trace_runner REPO_ROOT OUT_JSON [TEST_DIR]

Installs a ``sys.settrace`` tracer, runs the repo's own test suite
(stdlib ``unittest`` discovery) in-process, and writes the harvested
caller->callee pairs to OUT_JSON. Only frames whose file lives under
REPO_ROOT are recorded, and edgereckon's own frames are excluded.

Ground-truth honesty: a traced pair proves that call happened, in
that test run. Absence of a pair proves nothing -- the tests may
simply not exercise that path. The auditor's stamps honour that
asymmetry; so must anyone reading this file's output.
"""

import io
import json
import os
import sys
import threading
import unittest

_OWN_DIR = os.path.dirname(os.path.abspath(__file__))


def _module_for(filename: str, root: str):
    rel = os.path.relpath(filename, root)
    if rel.startswith("..") or not rel.endswith(".py"):
        return None
    parts = rel.replace(os.sep, "/").split("/")
    parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _frame_id(frame, root: str):
    filename = frame.f_code.co_filename
    if os.path.dirname(os.path.abspath(filename)) == _OWN_DIR:
        return None
    module = _module_for(filename, root)
    if module is None:
        return None
    qual = getattr(frame.f_code, "co_qualname", frame.f_code.co_name)
    return f"{module}:{qual}"


def main(argv) -> int:
    root = os.path.abspath(argv[1])
    out_path = argv[2]
    test_dir = argv[3] if len(argv) > 3 else "tests"
    os.chdir(root)
    sys.path.insert(0, root)

    pairs = set()
    executed = set()
    callers = set()

    def tracer(frame, event, arg):
        if event == "call":
            callee = _frame_id(frame, root)
            if callee is not None:
                executed.add(callee)
                back = frame.f_back
                if back is not None:
                    caller = _frame_id(back, root)
                    if caller is not None:
                        pairs.add((caller, callee))
                        callers.add(caller)
            return tracer
        return None

    start_dir = os.path.join(root, test_dir)
    result_info = {"tests_run": 0, "failures": 0, "errors": 0,
                   "ok": False, "load_error": ""}
    sys.settrace(tracer)
    threading.settrace(tracer)
    try:
        if os.path.isdir(start_dir):
            suite = unittest.TestLoader().discover(
                start_dir=start_dir, top_level_dir=root)
            runner = unittest.TextTestRunner(stream=io.StringIO(),
                                             verbosity=0)
            result = runner.run(suite)
            result_info.update({
                "tests_run": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "ok": bool(result.wasSuccessful()),
            })
        else:
            result_info["load_error"] = \
                f"test directory not found: {test_dir}"
    except Exception as exc:  # discovery/import failure = no ground truth
        result_info["load_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        sys.settrace(None)
        threading.settrace(None)

    payload = {
        "repo": root,
        "test_dir": test_dir,
        "pairs": sorted([list(p) for p in pairs]),
        "executed": sorted(executed),
        "callers": sorted(callers),
        **result_info,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
