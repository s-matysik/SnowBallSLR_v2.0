# ruff: noqa: E402
"""Recompute the screening-model tables of supplement S8 from the released scores, without calling any model.

    python validation/reproduce_screening_tables.py data/synergy_screening_scores.csv OUT_DIR

Reads one row per record (review, doi, included_by_authors, one column per model) and writes
metrics.csv (pooled AUC with percentile bootstrap intervals, sensitivity/specificity at 5 and 7, WSS)
and paired_differences.csv (AUC difference against the three reference models with Holm-adjusted p over
the distinct pairs; a bootstrap p of zero is floored at 1/2000). The bootstrap seed is fixed in compare_vendors.py.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_vendors as cv

MODELS = [('Claude Haiku 4.5', 'Anthropic'), ('Claude Sonnet 5', 'Anthropic'), ('Claude Opus 4.8', 'Anthropic'), ('GPT-5.4 mini', 'OpenAI'), ('GPT-5.4', 'OpenAI'), ('DeepSeek Flash', 'DeepSeek'), ('DeepSeek V4 Pro', 'DeepSeek'), ('Gemini 3.5 Flash', 'Google'), ('Gemini 3.1 Pro', 'Google'), ('Grok 4.20', 'xAI'), ('Grok 4.7', 'xAI')]
REFS = ["Claude Sonnet 5", "Claude Opus 4.8", "GPT-5.4"]


def main(scores_csv, out_dir):
    df = pd.read_csv(scores_csv)
    setd = df.rename(columns={"included_by_authors": "label"})[["review", "doi", "label"]]
    models = [(m, p, m) for m, p in MODELS]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        import json
        for m, _p, mid in models:
            col = df.set_index("doi")[m].dropna()
            (tmp / f"scores_{mid}.json").write_text(json.dumps(col.to_dict()))
        res = cv.analyse(setd, tmp, models, REFS)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    res["CMP"].to_csv(out / "metrics.csv", index=False)
    d = res["DIFF"].copy()
    d["pair"] = d.apply(lambda r: tuple(sorted([r.model, r.reference])), axis=1)
    d = d.drop_duplicates("pair").drop(columns="pair")
    d["p_floor"] = np.maximum(d.p_boot, 1 / cv.NBOOT)
    d = d.sort_values("p_floor").reset_index(drop=True)
    n = len(d)
    d["p_holm"] = np.minimum(1, np.maximum.accumulate([(n - i) * p for i, p in enumerate(d.p_floor)]))
    d.to_csv(out / "paired_differences.csv", index=False)
    print(f"{len(res['COMMON'])} records scored by every model; {n} distinct pairs; wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
