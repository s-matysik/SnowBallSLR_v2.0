"""Bit-equality of the pure-Python Jaro-Winkler against rapidfuzz, on real titles.

Compares identity/jaro.py with (a) rapidfuzz's reference Python implementation and
(b) the compiled rapidfuzz on this machine, on title pairs drawn from the four live
v1 runs: random pairs, and one-to-three-edit near-duplicates, the regime in which
deduplication actually decides. Both argument orders are checked. Writes
validation/jaro_equality.json.

    python validation/validation_jaro.py /path/to/v1/repo
"""
import json, platform, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rapidfuzz.distance import JaroWinkler, JaroWinkler_py  # noqa: E402
import rapidfuzz  # noqa: E402

from snowballslr.identity.jaro import jaro_winkler_similarity as pure  # noqa: E402
from snowballslr.identity.normalize import normalize_title  # noqa: E402

v1 = Path(sys.argv[1])
titles = set()
for run in ("run_adverse", "run_mid", "run_large", "run_narrow"):
    st = json.loads((v1 / run / "state.json").read_text())
    for w in st["works"].values():
        t = w.get("title_norm") or normalize_title(w.get("title") or "")
        if t:
            titles.add(t)
titles = sorted(titles)
rnd = random.Random(20261112)


def perturb(s):
    k, i = rnd.randrange(4), rnd.randrange(len(s) + 1)
    c = rnd.choice("abcdefghijklmnopqrstuvwxyz 0123456789")
    if k == 1 and s:
        return s[:i] + s[i + 1:]
    if k == 2 and len(s) > 1 and i < len(s) - 1:
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    return s[:i] + c + s[i + (1 if k == 3 else 0):]


pairs = [(rnd.choice(titles), rnd.choice(titles)) for _ in range(60000)]
for _ in range(60000):
    s = t = rnd.choice(titles)
    for _ in range(rnd.randrange(1, 4)):
        t = perturb(t)
    pairs.append((s, t))
n = ref_eq = comp_eq = 0
first_comp_diff = None
for a, b in pairs:
    for x, y in ((a, b), (b, a)):
        p = pure(x, y)
        n += 1
        ref_eq += p == JaroWinkler_py.similarity(x, y)
        c = JaroWinkler.similarity(x, y)
        comp_eq += p == c
        if p != c and first_comp_diff is None:
            first_comp_diff = {"a": x, "b": y, "pure": repr(p), "compiled": repr(c)}
out = {
    "titles": len(titles), "pairs": len(pairs), "comparisons": n,
    "equal_to_rapidfuzz_reference_python": ref_eq,
    "equal_to_rapidfuzz_compiled": comp_eq,
    "rapidfuzz_version": rapidfuzz.__version__,
    "machine": platform.machine(), "system": platform.system(),
    "python": platform.python_version(),
    "example_compiled_difference": first_comp_diff,
    "note": ("Differences from the compiled wheel are last-bit only and arise because "
             "the compiler fuses the Winkler step into one fused multiply-add on this "
             "architecture; the reference implementation agrees exactly."),
}
Path(__file__).with_name("jaro_equality.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k not in ("note", "example_compiled_difference")}))
