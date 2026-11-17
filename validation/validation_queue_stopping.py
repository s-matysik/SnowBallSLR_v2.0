"""Pillar B: within-iteration stopping, paired against full screening.

The 270 synthetic reviews of the version-1 stopping benchmark (3 regimes x 6 graphs x
3 seed-set sizes x 5 draws, seeds drawn as in reproduce.py) are each run through the
library to its own stopping rules five times:

  full          every candidate of every iteration is screened (version-1 behaviour)
  queue         the within-iteration rule, scope "queue"
  review        the within-iteration rule, scope "review"
  queue_random  as "queue", but each queue is screened in random order (control)
  review_random as "review", in random order (control)

The ranking uses citation structure only: the generator's titles and abstracts encode
relevance, so they are replaced by one neutral text before the run. A real ranking that
also uses text can only do better than this.

For each run the script records records screened, true recall at stop (found / all
relevant), and for every iteration cut short by the rule whether the recall target held
at that moment within the scope the test addresses. Output: one CSV row per run.

    python validation/validation_queue_stopping.py OUT.csv [--quick] [--workers 8]
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from validation_generator import GraphSpec, generate_graph  # noqa: E402

from snowballslr import Config  # noqa: E402
from snowballslr.core.run import Run  # noqa: E402

REGIMES = {
    "dense": dict(p_in=0.055, refs_mean=28, n_relevant=120, n_irrelevant=900),
    "sparse": dict(p_in=0.018, refs_mean=22, n_relevant=120, n_irrelevant=900),
    "diffuse": dict(p_in=0.055, refs_mean=28, n_relevant=120, n_irrelevant=2400),
}
SEED_SIZES = (5, 10, 20)
DRAWS = 5
VARIANTS = ("full", "queue", "review", "queue_random", "review_random")
TARGET, ALPHA, MAX_ITER = 0.95, 0.05, 12
FIELDS = ["regime", "graph_seed", "seed_size", "draw", "variant", "n_gold", "iterations",
          "stopped_by", "screened", "found", "recall", "queues_cut", "records_left_unscreened",
          "cuts_below_target"]


def cells(quick: bool):
    for regime, kw in REGIMES.items():
        for gseed in (range(2) if quick else range(6)):
            g = generate_graph(GraphSpec(seed=gseed, **kw))
            gold = sorted(g["gold"])
            rng = random.Random(2000 + gseed)
            for size in SEED_SIZES:
                for draw in range(1 if quick else DRAWS):
                    yield regime, gseed, size, draw, rng.sample(gold, size)


def neutral_graph(g):
    works = {}
    for k, w in g["works"].items():
        w = dict(w)
        w["title"] = "A study on citation searching"
        w["abstract"] = "citation searching systematic review"
        works[k] = w
    return {"works": works, "references": g["references"], "citations": g["citations"]}


def config(variant: str) -> Config:
    d = {"run": {"max_iterations": MAX_ITER},
         "ranking": {"components": ["network"]}}
    if variant != "full":
        d["stopping"] = {"within_iteration": {"target": TARGET, "alpha": ALPHA,
                                              "scope": variant.split("_")[0]}}
    return Config.model_validate(d)


def one(args):
    regime, gseed, size, draw, seeds, variant = args
    g = generate_graph(GraphSpec(seed=gseed, **REGIMES[regime]))
    gold = set(g["gold"])
    graph = neutral_graph(g)
    rng = random.Random(f"{regime}|{gseed}|{size}|{draw}|order")
    with tempfile.TemporaryDirectory() as tmp:
        run = Run.init(Path(tmp) / "r", seeds, config(variant), offline_graph=graph)
        cut = left = below = 0
        while not run.stopped and run.state.iteration < MAX_ITER:
            cands = run.step()
            if not cands:
                break
            order = [w.key for w in cands]
            if variant.endswith("random"):
                rng.shuffle(order)
                # Screening order is the queue order: re-rank pending to match.
                run.state.pending = list(order)
            if variant == "full":
                run.label({k: ("include" if k in gold else "exclude") for k in order})
                continue
            decided: dict[str, str] = {}
            stop_at = len(order)
            for j, k in enumerate(order):
                decided[k] = "include" if k in gold else "exclude"
                if j + 1 < len(order) and (j + 1) % 5 == 0 and run.queue_test(decided)["stop"]:
                    stop_at = j + 1
                    break
            if stop_at < len(order):
                cut += 1
                left += len(order) - stop_at
                qt = run.queue_test(decided)
                if qt["scope"] == "queue":
                    rel_q = sum(1 for k in order if k in gold)
                    rec = (qt["n_relevant"] / rel_q) if rel_q else 1.0
                else:
                    # Recall over every record identified so far that is relevant.
                    seen_rel = qt["prior_relevant"] + qt["n_relevant"]
                    unseen_rel = sum(1 for k in order[stop_at:] if k in gold) + sum(
                        1 for q in run.state.queue_tests for k in q.get("left_unscreened", ())
                        if k in gold and k not in run.state.decisions and k not in set(order))
                    rec = seen_rel / (seen_rel + unseen_rel) if seen_rel + unseen_rel else 1.0
                below += rec < TARGET
            run.label(decided)
        found = len(set(run.state.included_keys) & gold)
        last = run.state.history.last
        row = dict(regime=regime, graph_seed=gseed, seed_size=size, draw=draw, variant=variant,
                   n_gold=len(gold), iterations=len(run.state.history),
                   stopped_by=run.state.stopped_by or "max_iterations",
                   screened=last.cumulative_screened if last else 0, found=found,
                   recall=round(found / len(gold), 4), queues_cut=cut,
                   records_left_unscreened=left, cuts_below_target=below)
        run.close()
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    a = ap.parse_args()
    jobs = [(*c, v) for c in cells(a.quick) for v in a.variants.split(",")]
    with ProcessPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, jobs, chunksize=2))
    rows.sort(key=lambda r: (r["regime"], r["graph_seed"], r["seed_size"], r["draw"],
                             VARIANTS.index(r["variant"])))
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} runs -> {a.out}")


if __name__ == "__main__":
    main()
