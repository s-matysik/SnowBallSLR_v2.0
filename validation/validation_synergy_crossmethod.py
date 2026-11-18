"""Cross-method recall on real reviews with known truth (SYNERGY+ x Scopus).

Truth: the review authors' included studies T. Database arm D: inclusions retrieved by an independent
Scopus search (database_searches.json). Seeds: five studies drawn from D, as a reviewer would start from
database results. Citation arm C: inclusions found by SnowBallSLR from the seeds on the Scopus graph,
screened with the authors' labels, run to its own stopping rules. Chapman over D minus seeds and C
estimates |T minus seeds|, which is known.

    python validation_synergy_crossmethod.py RAW_DIR SEARCHES.json OUT.csv
"""
import csv
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from validation_synergy_scopus import MAX_ITER, build_graph, config, key  # noqa: E402

from snowballslr.core.run import Run  # noqa: E402
from snowballslr.estimate.capture_recapture import chapman  # noqa: E402

SEEDS, DRAWS, MIN_DB = 5, 5, 10
FIELDS = ["review", "draw", "truth", "n_database", "n_citation", "m", "observed", "true_recall", "stopped_by", "screened",
          "chapman_estimable", "chapman_n_hat", "chapman_lo", "chapman_hi", "chapman_covers", "chapman_rel_bias",
          "est_recall", "est_recall_lo", "est_recall_hi", "reason"]

def main(raw_dir, searches, out):
    S = json.loads(Path(searches).read_text())["reviews"]
    rows = []
    for p in sorted(Path(raw_dir).glob("*.json")):
        raw = json.loads(p.read_text())
        rv = raw["review"]
        T = {key(e) for e in raw["included_mapped"]}
        D = sorted(key(e) for e in S[rv]["db_included"])
        if len(D) < MIN_DB:
            continue
        graph = build_graph(raw)
        for draw in range(DRAWS):
            seeds = sorted(random.Random(f"{rv}|db|{draw}").sample(D, SEEDS))
            with tempfile.TemporaryDirectory() as tmp:
                run = Run.init(Path(tmp) / "r", seeds, config(None), offline_graph=graph)
                while not run.stopped and run.state.iteration < MAX_ITER:
                    c = run.step()
                    if not c:
                        break
                    run.label({w.key: ("include" if w.key in T else "exclude") for w in c})
                C = (set(run.state.included_keys) & T) - set(seeds)
                stopped, screened = run.state.stopped_by or "max_iterations", run.state.history.last.cumulative_screened
                run.close()
            Dp = set(D) - set(seeds)
            truth = len(T - set(seeds))
            n1, n2, m = len(Dp), len(C), len(Dp & C)
            obs = len(Dp | C)
            r = chapman(n1, n2, m, n_observed=obs)
            row = dict(review=rv, draw=draw, truth=truth, n_database=n1, n_citation=n2, m=m, observed=obs,
                       true_recall=round(obs / truth, 4), stopped_by=stopped, screened=screened,
                       chapman_estimable=bool(r.estimable and r.n_hat), reason=r.reason or "")
            if row["chapman_estimable"]:
                lo, hi = r.n_hat_ci
                row.update(chapman_n_hat=round(r.n_hat, 2), chapman_lo=round(lo, 2), chapman_hi=round(hi, 2),
                           chapman_covers=lo <= truth <= hi, chapman_rel_bias=round((r.n_hat - truth) / truth, 4),
                           est_recall=round(obs / r.n_hat, 4), est_recall_lo=round(obs / hi, 4), est_recall_hi=round(min(1, obs / lo), 4))
            rows.append(row)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows ->", out)

if __name__ == "__main__":
    main(*sys.argv[1:4])
