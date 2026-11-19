"""Real-data stopping benchmark: SYNERGY reviews on their Scopus citation graph.

Ground truth is each review's own list of included studies (SYNERGY dataset; labels
made by the review authors). The citation graph is Scopus (synergy_scopus_crawl.py):
references and citing works of every included study. A run starts from five randomly
drawn included studies and screens each queue with the authors' labels: a candidate is
included if and only if the review included it. Candidates the review never screened
count as excluded, so recall is recall of the review's own inclusions.

Titles are real (Scopus); abstracts are not retrieved, so the ranking uses titles and
citation structure (library default: BM25 + network, fused by RRF).

Variants per (review, draw): full screening (version 1) and the within-iteration rule
(scope review) at alpha 0.05 and 0.01.

    python validation/validation_synergy_scopus.py RAW_DIR OUT.csv [--shard I/N]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from snowballslr import Config  # noqa: E402
from snowballslr.core.run import Run  # noqa: E402

SEEDS, DRAWS, TARGET, MAX_ITER = 5, 5, 0.95, 10
VARIANTS = (("full", None), ("review", 0.05), ("review", 0.01))
FIELDS = ["review", "draw", "variant", "alpha", "n_included_mapped", "n_target", "reachable", "iterations",
          "stopped_by", "screened", "found", "recall", "recall_of_reachable", "queues_cut",
          "records_left_unscreened", "cuts_below_target", "v1_rules_fired"]


def key(eid):
    return f"scopus:{eid}"


def build_graph(raw):
    works, refs, cits = {}, {}, {}

    def add(eid, title, year, doi):
        k = key(eid)
        if k not in works or (not works[k]["title"] and title):
            works[k] = {"title": title or "", "abstract": "", "year": int(year) if str(year or "").isdigit() else None,
                        "doi": doi, "authors": [], "type": "article", "venue": "", "language": "en",
                        "cited_by_count": 0, "reference_count": 0, "is_retracted": False, "provenance": [],
                        "source_ids": {"scopus": eid}, "title_norm": "", "unresolved": False}
        return k

    for eid, rec in raw["expanded"].items():
        k = add(eid, rec["title"], rec["year"], rec["doi"])
        works[k]["cited_by_count"] = rec["cited_by"]
        refs[k] = [add(r["eid"], r["title"], r["year"], r["doi"]) for r in rec["references"]]
        cits[k] = [add(c["eid"], c["title"], c["year"], c["doi"]) for c in rec["citing"]]
        works[k]["reference_count"] = len(refs[k])
    return {"works": works, "references": refs, "citations": cits}


def reachable(graph, seeds, gold):
    seen, frontier = set(seeds), list(seeds)
    while frontier:
        nxt = []
        for k in frontier:
            for n in graph["references"].get(k, []) + graph["citations"].get(k, []):
                if n in gold and n not in seen:
                    seen.add(n)
                    nxt.append(n)
        frontier = nxt
    return seen - set(seeds)


def config(alpha):
    d = {"run": {"max_iterations": MAX_ITER}}
    if alpha is not None:
        d["stopping"] = {"within_iteration": {"target": TARGET, "alpha": alpha, "scope": "review"}}
    return Config.model_validate(d)


def one(raw, draw, variant, alpha, every=5):
    graph = build_graph(raw)
    gold = {key(e) for e in raw["included_mapped"]}
    seeds = sorted(random.Random(f"{raw['review']}|{draw}").sample(sorted(gold), SEEDS))
    target = gold - set(seeds)
    reach = reachable(graph, seeds, gold)
    with tempfile.TemporaryDirectory() as tmp:
        run = Run.init(Path(tmp) / "r", seeds, config(alpha), offline_graph=graph)
        cut = left = below = 0
        fired = set()
        while not run.stopped and run.state.iteration < MAX_ITER:
            cands = run.step()
            if not cands:
                break
            order = [w.key for w in cands]
            if alpha is None:
                run.label({k: ("include" if k in gold else "exclude") for k in order})
            else:
                decided, stop_at = {}, len(order)
                for j, k in enumerate(order):
                    decided[k] = "include" if k in gold else "exclude"
                    if j + 1 < len(order) and (j + 1) % every == 0 and run.queue_test(decided)["stop"]:
                        stop_at = j + 1
                        break
                if stop_at < len(order):
                    cut += 1
                    left += len(order) - stop_at
                    qt = run.queue_test(decided)
                    seen_rel = qt["prior_relevant"] + qt["n_relevant"]
                    unseen_rel = sum(1 for k in order[stop_at:] if k in gold) + sum(
                        1 for q in run.state.queue_tests for k in q.get("left_unscreened", ())
                        if k in gold and k not in run.state.decisions and k not in set(order))
                    below += (seen_rel / (seen_rel + unseen_rel) if seen_rel + unseen_rel else 1.0) < TARGET
                run.label(decided)
            last = run.state.history.last
            for name, dec in (getattr(last, "rule_decisions", None) or {}).items():
                if dec.get("triggered") if isinstance(dec, dict) else dec:
                    fired.add(name)
        found = len(set(run.state.included_keys) & target)
        last = run.state.history.last
        row = dict(review=raw["review"], draw=draw, variant=variant if alpha is None else f"{variant}_{alpha}",
                   alpha=alpha if alpha is not None else "", n_included_mapped=len(gold), n_target=len(target),
                   reachable=len(reach), iterations=len(run.state.history),
                   stopped_by=run.state.stopped_by or "max_iterations",
                   screened=last.cumulative_screened if last else 0, found=found,
                   recall=round(found / len(target), 4) if target else "",
                   recall_of_reachable=round(found / len(reach), 4) if reach else "",
                   queues_cut=cut, records_left_unscreened=left, cuts_below_target=below,
                   v1_rules_fired=";".join(sorted(fired)))
        run.close()
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--draws", type=int, default=DRAWS)
    ap.add_argument("--check-every", type=int, default=5, help="evaluate the rule after every N decisions (the published benchmark uses 5; the application uses 1)")
    ap.add_argument("--variants", default="", help="comma-separated subset, e.g. review_0.05")
    a = ap.parse_args()
    raws = [json.loads(p.read_text()) for p in sorted(Path(a.raw).glob("*.json"))]
    jobs = [(r, d, v, al) for r in raws if len(r["included_mapped"]) > SEEDS + 5
            for d in range(a.draws) for v, al in VARIANTS]
    i, n = (int(x) for x in a.shard.split("/"))
    if a.variants:
        keep = set(a.variants.split(","))
        jobs = [j for j in jobs if (j[2] if j[3] is None else f"{j[2]}_{j[3]}") in keep]
    rows = [one(*j, every=a.check_every) for j in jobs[i::n]]
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} runs -> {a.out}")


if __name__ == "__main__":
    main()
