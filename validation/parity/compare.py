"""Compare CPython and Pyodide parity fingerprints; exit non-zero on any difference.

    python compare.py cpython.json pyodide.json [results.json]
"""
import json
import sys

KEYS = ("config_hash", "stopped_by", "outputs", "iterations", "candidate_order", "estimate")
from pathlib import Path

a, b = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
res = {
    "cpython": {"runtime": a["runtime"], "python": a["python"]},
    "pyodide": {"runtime": b["runtime"], "python": b["python"]},
    "snowballslr": a["snowballslr"],
    "artifacts_compared": len(a["outputs"]),
    "artifacts_differing": sorted(n for n in a["outputs"] if a["outputs"][n] != b["outputs"].get(n)),
    "fields_identical": {k: a[k] == b[k] for k in KEYS},
    "pyodide_verifies_cpython_archive": b.get("verify_other", {}).get("ok"),
    "cpython_verifies_pyodide_archive": a.get("verify_other", {}).get("ok"),
}
res["identical"] = all(res["fields_identical"].values()) and not res["artifacts_differing"]
print(json.dumps(res, indent=1))
if len(sys.argv) > 3:
    Path(sys.argv[3]).write_text(json.dumps(res, indent=1) + "\n")
sys.exit(0 if res["identical"] and res["pyodide_verifies_cpython_archive"] is not False else 1)
