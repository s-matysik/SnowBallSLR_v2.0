"""Verify, with the command-line library, the archives the browser test downloaded.

    python check_archives.py E2E_OUT

Appends the result to E2E_OUT/e2e.json and exits non-zero unless every archive
replays from its own cache and every recorded output matches.
"""
import json
import sys
from pathlib import Path

from snowballslr.web import verify_archive

out = Path(sys.argv[1])
res = json.loads((out / "e2e.json").read_text())
checks = {}
for z in sorted(out.glob("*_run.zip")):
    r = verify_archive(z.read_bytes())
    checks[z.name] = {"ok": r["ok"], "artifacts_checked": r.get("artifacts_checked"),
                      "mismatched": r.get("artifacts_mismatched"), "error": r.get("error")}
    print(z.name, checks[z.name])
res["cli_verification"] = checks
(out / "e2e.json").write_text(json.dumps(res, indent=1))
assert checks and all(c["ok"] for c in checks.values()), checks
