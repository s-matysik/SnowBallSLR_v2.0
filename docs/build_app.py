"""Assemble the browser app into a site directory.

    python docs/build_app.py --out _site

Copies docs/app (index.html and the offline demo graph), builds the package
wheel from this checkout into the same directory, and writes wheel.json naming
it, so the published app always runs exactly the code at this commit.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--out", default="_site")
a = ap.parse_args()
dest = Path(a.out) / "app"
if dest.exists():
    shutil.rmtree(dest)
shutil.copytree(ROOT / "docs" / "app", dest)
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", tmp, str(ROOT)], check=True)
    wheels = sorted(Path(tmp).glob("snowballslr-*.whl"))
    assert len(wheels) == 1, wheels
    shutil.copy(wheels[0], dest / wheels[0].name)
    (dest / "wheel.json").write_text(json.dumps({"wheel": wheels[0].name}) + "\n")
print(f"app assembled in {dest} with {wheels[0].name}")
