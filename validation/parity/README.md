# Browser-CLI parity

`case.py` runs a complete review on the offline fixture graph through the browser
session API (`snowballslr.web.Session`) and writes a fingerprint: every artifact hash in
the run manifest, every per-iteration record, the candidate order at each iteration, the
recall estimate and the stop rule. The same file is executed by CPython and, through
`run_pyodide.mjs`, by Pyodide 0.28.3 under Node. `compare.py` requires the fingerprints to be
identical, and each runtime also verifies the archive the other produced.

```bash
python -m build -w .
FIXTURES=tests/fixtures OUT=/tmp/cpython.json python validation/parity/case.py
cd validation/parity && npm install pyodide@0.28.3
node run_pyodide.mjs ../../dist/*.whl ../../tests/fixtures /tmp/pyodide.json /tmp/cpython.zip
python compare.py /tmp/cpython.json /tmp/pyodide.json results.json
```

Archives are not byte-identical between runs: `run.json` and `state.json` carry wall-clock
timestamps. Everything the review computed is.
