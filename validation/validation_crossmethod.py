"""Pillar A: cross-method recall estimation (database search arm vs citation-chase arm).

Implements the design fixed in PREREGISTRATION_pillar_A.md. One CSV row per
(review, q, rho, depth) with the Chapman and Chao1 estimates against known truth.

    python validation/validation_crossmethod.py OUT.csv [--quick]
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from validation_generator import GraphSpec, generate_graph  # noqa: E402

from snowballslr.estimate.capture_recapture import chapman  # noqa: E402
from snowballslr.estimate.chao import chao1  # noqa: E402

REGIMES = {
    "dense": dict(p_in=0.055, refs_mean=28, n_relevant=120, n_irrelevant=900),
    "sparse": dict(p_in=0.018, refs_mean=22, n_relevant=120, n_irrelevant=900),
    "diffuse": dict(p_in=0.055, refs_mean=28, n_relevant=120, n_irrelevant=2400),
}
SEED_SIZES, DRAWS = (5, 10, 20), 5
QS, RHOS = (0.5, 0.7, 0.85), (0.0, 0.3, 0.6)
MAX_DEPTH = 12
FIELDS = ["regime", "graph_seed", "seed_size", "draw", "q", "rho", "depth", "at_exhaustion",
          "truth", "n_db", "n_chase", "m", "observed", "chapman_estimable", "chapman_n_hat",
          "chapman_lo", "chapman_hi", "chapman_rel_bias", "chapman_covers",
          "chao1_estimable", "chao1_n_hat", "chao1_lo", "chao1_hi", "chao1_rel_bias",
          "chao1_covers"]


def latent_of(g):
    return g["latent"]


def chase_by_depth(g, seeds, gold):
    """Relevant records reached by perfect-screening citation chasing, per depth."""
    refs_p = g["provider_edges"]
    fwd = {}
    for pj, edges in refs_p.items():
        rev = {}
        for s, ts in edges.items():
            for t in ts:
                rev.setdefault(t, []).append(s)
        fwd[pj] = rev
    decided, included = set(seeds), set()
    frontier, out = list(seeds), []
    for _ in range(MAX_DEPTH):
        if not frontier:
            break
        new = set()
        for p in frontier:
            for pj in refs_p:
                new.update(t for t in refs_p[pj].get(p, ()) if t not in decided)
                new.update(s for s in fwd[pj].get(p, ()) if s not in decided)
        if not new:
            break
        decided |= new
        hits = sorted(new & gold)
        included |= set(hits)
        frontier = hits
        out.append(set(included))
    return out


def evaluate(truth, db, chase):
    n1, n2, m = len(db), len(chase), len(db & chase)
    obs = len(db | chase)
    row = dict(truth=truth, n_db=n1, n_chase=n2, m=m, observed=obs)
    e = chapman(n1, n2, m, n_observed=obs)
    row["chapman_estimable"] = bool(e.estimable and e.n_hat is not None)
    if row["chapman_estimable"]:
        lo, hi = e.n_hat_ci
        row.update(chapman_n_hat=round(e.n_hat, 2), chapman_lo=round(lo, 2), chapman_hi=round(hi, 2),
                   chapman_rel_bias=round((e.n_hat - truth) / truth, 4),
                   chapman_covers=lo <= truth <= hi)
    hist = {k: [a for a, s in (("db", db), ("chase", chase)) if k in s] for k in db | chase}
    c = chao1(hist)
    row["chao1_estimable"] = bool(c.estimable and c.n_hat is not None)
    if row["chao1_estimable"]:
        lo, hi = c.n_hat_ci if c.n_hat_ci else (None, None)
        row.update(chao1_n_hat=round(c.n_hat, 2), chao1_rel_bias=round((c.n_hat - truth) / truth, 4))
        if lo is not None:
            row.update(chao1_lo=round(lo, 2), chao1_hi=round(hi, 2), chao1_covers=lo <= truth <= hi)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    rows = []
    for regime, kw in REGIMES.items():
        for gseed in (range(2) if a.quick else range(6)):
            g = generate_graph(GraphSpec(seed=gseed, **kw))
            gold = set(g["gold"])
            lat = latent_of(g)
            for q in QS:
                for rho in RHOS:
                    rng_db = random.Random(f"db|{regime}|{gseed}|{q}|{rho}")
                    db_all = {k for k in sorted(gold)
                              if rho * lat[k] + (1 - rho) * rng_db.random() > 1 - q}
                    rng = random.Random(2000 + gseed)
                    for size in SEED_SIZES:
                        for draw in range(1 if a.quick else DRAWS):
                            pool = sorted(db_all)
                            if len(pool) < size:
                                continue
                            seeds = set(rng.sample(pool, size))
                            truth = len(gold) - len(seeds)
                            db = db_all - seeds
                            curve = chase_by_depth(g, seeds, gold)
                            for d, chase in enumerate(curve, start=1):
                                r = evaluate(truth, db, chase - seeds)
                                r.update(regime=regime, graph_seed=gseed, seed_size=size, draw=draw,
                                         q=q, rho=rho, depth=d, at_exhaustion=d == len(curve))
                                rows.append(r)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    prim = [r for r in rows if r["rho"] == 0.3 and r["at_exhaustion"] and r["chapman_estimable"]]
    n_all = sum(1 for r in rows if r["rho"] == 0.3 and r["at_exhaustion"])
    cov = sum(r["chapman_covers"] for r in prim) / len(prim)
    bias = st.median(r["chapman_rel_bias"] for r in prim)
    print(f"{len(rows)} rows | primary: {len(prim)}/{n_all} estimable, coverage {cov:.3f}, "
          f"median rel. bias {bias:+.4f} -> {'GO' if cov >= 0.80 and abs(bias) <= 0.05 else 'NO-GO'}")


if __name__ == "__main__":
    main()
