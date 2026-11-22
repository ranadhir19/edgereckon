"""Ground-truth harvesting: run the target repo's tests under trace.

The trace runner executes as a subprocess with the edgereckon package
importable, the target repo as cwd, and a hard timeout. Any failure --
no test directory, discovery error, timeout, non-zero exit -- yields
``None`` plus a human-readable note, and the audit proceeds with
NO_GROUND_TRUTH stamps rather than pretending.
"""

import json
import os
import subprocess
import sys
import tempfile


def harvest_trace(repo: str, test_dir: str = "tests",
                  timeout: int = 600):
    """Return (trace_dict_or_None, note)."""
    package_parent = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = package_parent + os.pathsep + env.get("PYTHONPATH", "")
    with tempfile.TemporaryDirectory() as td:
        out_path = os.path.join(td, "trace.json")
        cmd = [sys.executable, "-m", "edgereckon.trace_runner",
               os.path.abspath(repo), out_path, test_dir]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  env=env, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, f"trace run timed out after {timeout}s"
        if proc.returncode != 0 or not os.path.exists(out_path):
            tail = (proc.stderr or "").strip().splitlines()
            note = tail[-1] if tail else f"exit code {proc.returncode}"
            return None, f"trace runner failed: {note}"
        with open(out_path, encoding="utf-8") as fh:
            trace = json.load(fh)
    if trace.get("load_error"):
        return None, f"no ground truth: {trace['load_error']}"
    if trace.get("tests_run", 0) == 0:
        return None, "no ground truth: test suite ran zero tests"
    return trace, "ok"
