"""One parity case, executed unchanged by CPython and by Pyodide.

Drives a complete review on the offline fixture graph through the browser
session API, then emits a JSON fingerprint of everything the run computed:
every artifact hash in the manifest, every per-iteration record (counts,
content hashes and stop decisions), the configuration hash and the stop rule.
Timestamps are excluded because they are wall-clock by design.

Inputs are read from FIXTURES (a directory) and the result is written to OUT.
"""
import json
import os
import sys
from pathlib import Path

from snowballslr import __version__
from snowballslr.simulation.oracle import Oracle
from snowballslr.web import Session, pack, verify_archive

fx = Path(os.environ["FIXTURES"])
graph = json.loads((fx / "mini_graph.json").read_text(encoding="utf-8"))
oracle = Oracle.from_file(fx / "mini_gold.csv")
seeds = sorted(oracle.included)[:3]

s = Session(Path(os.environ.get("WORKDIR", "/tmp/parity-work")))
s.new(seeds, offline_graph=graph)
steps = []
for _ in range(10):
    out = s.step()
    steps.append([c["key"] for c in out["candidates"]])
    if out["stopped"] or not out["candidates"]:
        break
    s.label({c["key"]: ("include" if c["key"] in oracle.included else "exclude")
             for c in out["candidates"]})
s.report()
m = json.loads((s.run.root / "run.json").read_text(encoding="utf-8"))
archive = pack(s.run.root)
other = os.environ.get("VERIFY_ARCHIVE")
fp = {
    "runtime": sys.platform,
    "python": sys.version.split()[0],
    "snowballslr": __version__,
    "config_hash": m["config_hash"],
    "stopped_by": m.get("stopped_by"),
    "outputs": m["outputs"],
    "iterations": m["iterations"],
    "candidate_order": steps,
    "self_verify_ok": verify_archive(archive)["ok"],
    "estimate": s.estimate(),
}
if other:
    fp["verify_other"] = verify_archive(Path(other).read_bytes())
Path(os.environ["OUT"]).write_text(json.dumps(fp, indent=1, sort_keys=True, default=str))
Path(os.environ["OUT"]).with_suffix(".zip").write_bytes(archive)
print("ok", fp["stopped_by"], len(fp["outputs"]), "artifacts")
